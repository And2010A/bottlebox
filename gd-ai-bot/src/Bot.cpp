#include "Bot.hpp"

#include <Geode/Geode.hpp>
#include <Geode/ui/Notification.hpp>
#include <Geode/utils/file.hpp>
#include <fmt/chrono.h>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstring>
#include <fstream>

using namespace geode::prelude;
using namespace aibot;

namespace {
    // A death this close after a moment means that moment was probably a
    // mistake, so it is not learned from.
    constexpr int kUnsafeTicks = 120;

    // Stable across runs and platforms, unlike std::hash.
    uint64_t fnv1a(std::string_view text) {
        uint64_t hash = 0xcbf29ce484222325ull;
        for (unsigned char c : text) {
            hash ^= c;
            hash *= 0x100000001b3ull;
        }
        return hash;
    }

    std::string levelKeyFor(PlayLayer* layer) {
        auto level = layer->m_level;
        std::string key;
        int id = level ? level->m_levelID.value() : 0;
        if (id > 0) {
            key = fmt::format("{}", id);
        }
        else {
            std::string name = level ? std::string(level->m_levelName) : std::string();
            key = fmt::format("local-{:016x}", fnv1a(name));
        }
        // A start position is a different run entirely.
        if (layer->m_startPosObject) {
            key += fmt::format("-sp{}", (int)layer->m_startPosObject->getPositionX());
        }
        return key;
    }

    std::filesystem::path saveDir() {
        return Mod::get()->getSaveDir();
    }

    std::filesystem::path macroDir() {
        return saveDir() / "macros";
    }

    // Keeps file names plain ASCII so every system can open them.
    std::string safeFileName(std::string const& name) {
        std::string out;
        for (unsigned char c : name) {
            if (c < 0x80 && (std::isalnum(c) || c == ' ' || c == '-' || c == '_')) out += (char)c;
            else if (c >= 0x80 || c == '.' || c == '/' || c == '\\') out += '_';
        }
        if (out.size() > 40) out.resize(40);
        while (!out.empty() && out.back() == ' ') out.pop_back();
        return out.empty() ? "level" : out;
    }

    char const* modeLabel(LearnMode mode) {
        switch (mode) {
            case LearnMode::Memory: return "Memory";
            case LearnMode::Human: return "Human";
            case LearnMode::Macro: return "Macro";
        }
        return "?";
    }

    bool clicksMatterInAir(int mode) {
        // A cube, ball or spider in mid-air ignores clicks unless an orb is near.
        return mode != Cube && mode != Ball && mode != Spider;
    }

    // True when pressing cannot change anything for this player right now:
    // a cube, ball or spider in mid-air with no orb in view, or a robot in
    // mid-air that is not already holding its jump.
    bool clickIsIdle(PlayerObject* player, int mode, float const* inputs, std::vector<uint8_t> const& run, uint8_t bit) {
        if (player->m_isOnGround) return false;
        for (int col = 0; col < kGridCols; col++) {
            for (int row = 0; row < kGridRows; row++) {
                if (inputs[gridIndex(OrbChannel, col, row)] > 0.5f) return false;
            }
        }
        if (mode == Cube || mode == Ball || mode == Spider) return true;
        if (mode == Robot) return run.empty() || !(run.back() & bit);
        return false;
    }

    bool orbInView(Sample const& sample) {
        for (int col = 0; col < kGridCols; col++) {
            for (int row = 0; row < kGridRows; row++) {
                int i = gridIndex(OrbChannel, col, row);
                if ((sample.grid[i / 8] >> (i % 8)) & 1) return true;
            }
        }
        return false;
    }
}

Bot& Bot::get() {
    static Bot instance;
    return instance;
}

Bot::Bot() : m_rng(std::random_device{}()) {
    this->reloadConfig();
}

void Bot::reloadConfig() {
    auto mod = Mod::get();
    m_config.enabled = mod->getSettingValue<bool>("enabled");
    auto mode = mod->getSettingValue<std::string>("mode");
    m_config.mode = mode == "Human" ? LearnMode::Human : mode == "Macro" ? LearnMode::Macro : LearnMode::Memory;
    m_config.learning = mod->getSettingValue<bool>("learning");
    m_config.speed = (float)mod->getSettingValue<double>("speed");
    m_config.reactionMs = (int)mod->getSettingValue<int64_t>("reaction-ms");
    m_config.jitterMs = (int)mod->getSettingValue<int64_t>("jitter-ms");
    m_config.lapsePercent = (float)mod->getSettingValue<double>("lapse-percent");
    m_config.showHud = mod->getSettingValue<bool>("show-hud");
}

std::filesystem::path Bot::memoryPath() const {
    return saveDir() / "memory" / (m_levelKey + ".bin");
}

bool Bot::canControl(PlayLayer* layer) const {
    return m_config.enabled && layer && !layer->m_isPracticeMode && !layer->m_isPlatformer;
}

bool Bot::isPlaying(PlayLayer* layer) const {
    return layer && layer == m_layer && m_config.enabled && m_attemptPrepared && !m_attemptEnded;
}

void Bot::detach() {
    this->pollTraining();
    this->saveMemory();
    this->saveBrain();
    m_layer = nullptr;
    m_hud = nullptr;
    m_sensors.clear();
    m_attemptPrepared = false;
    this->applySpeed();
}

void Bot::onLevelEnter(PlayLayer* layer) {
    this->detach();

    m_layer = layer;
    m_usedThisLevel = false;
    m_attemptPrepared = false;
    m_attemptEnded = false;
    m_lastTick = -1;
    m_lastEvent.clear();
    m_levelKey.clear();
    m_sensors.clear();
    this->reloadConfig();

    if (!layer) return;
    this->ensureBrain();

    m_levelName = layer->m_level ? std::string(layer->m_level->m_levelName) : std::string();

    auto winSize = CCDirector::get()->getWinSize();
    m_hud = CCLabelBMFont::create("", "chatFont.fnt");
    m_hud->setAnchorPoint({0.f, 1.f});
    m_hud->setPosition({6.f, winSize.height - 6.f});
    m_hud->setScale(0.5f);
    m_hud->setID("ai-bot-hud"_spr);
    layer->addChild(m_hud, 1000);

    this->applySpeed();
    this->updateHud(layer);
}

void Bot::onLevelExit(PlayLayer* layer) {
    if (layer && layer == m_layer) this->detach();
}

void Bot::onAttemptStart(PlayLayer* layer) {
    if (!layer || layer != m_layer) return;
    this->reloadConfig();
    this->pollTraining();

    auto key = levelKeyFor(layer);
    if (key != m_levelKey) {
        this->saveMemory();
        m_levelKey = key;
        m_memory.load(this->memoryPath());
        this->loadStates();
        m_learnedUpTo = 0;
        m_humanBest = 0.f;
        m_stuckAttempts = 0;
        m_levelAttempts = 0;
        m_beatenThisVisit = false;
    }

    m_attemptEnded = false;
    m_lastTick = -1;
    m_attemptPercent = 0.f;
    m_pressed[0] = m_pressed[1] = false;
    m_forceSync = true;
    m_runSamples[0].clear();
    m_runSamples[1].clear();
    m_runInputs.clear();
    m_runStates.clear();
    m_syncFixes = 0;
    m_lastX[0] = m_lastX[1] = 0.f;
    m_dx[0] = m_dx[1] = 0.f;

    m_attemptPrepared = this->canControl(layer);
    if (m_attemptPrepared) m_usedThisLevel = true;
    // Once the bot has played here, nothing until leaving the level counts
    // as the player's own progress (like playing from a start position).
    if (m_usedThisLevel) layer->m_isTestMode = true;

    if (m_attemptPrepared) {
        m_levelAttempts++;
        switch (m_config.mode) {
            case LearnMode::Memory: {
                this->ensureBrain();
                m_sensors.prepare(layer);
                m_memory.beginAttempt(m_config.learning, m_rng);
                break;
            }
            case LearnMode::Human: {
                this->ensureBrain();
                m_sensors.prepare(layer);
                m_hands.reset();
                m_humanAttempts++;
                // Stuck at the same spot for a while: try bolder ideas, like a
                // player who starts experimenting.
                float wild = (!m_config.learning || m_humanBest >= 100.f)
                    ? 0.f : std::min(0.3f, m_stuckAttempts / 100.f);
                std::uniform_real_distribution<float> spread(-1.f, 1.f);
                m_threshold = m_config.learning ? 0.5f + (0.08f + 0.15f * wild) * spread(m_rng) : 0.5f;
                m_deviationRate = m_config.learning ? (1.f + 4.f * wild) / 600.f : 0.f;
                m_deviateUntil[0] = m_deviateUntil[1] = -1;
                break;
            }
            case LearnMode::Macro: {
                if (m_macroKey != m_levelKey) this->loadMacro();
                break;
            }
        }
    }

    this->applySpeed();
    this->updateHud(layer);
}

void Bot::press(PlayLayer* layer, int player, bool down) {
    if (!m_forceSync && m_pressed[player] == down) return;
    m_sendingInput = true;
    layer->handleButton(down, 1, player == 0);
    m_sendingInput = false;
    m_pressed[player] = down;
}

void Bot::record(int tick, int player, float const* inputs, int mode, bool hold) {
    auto& run = m_runSamples[player];
    auto sample = makeSample(inputs, mode, hold);
    while ((int)run.size() < tick) run.push_back(sample);
    if ((int)run.size() == tick) run.push_back(sample);
}

void Bot::onTick(PlayLayer* layer) {
    if (!layer || layer != m_layer) return;

    int tick = (int)layer->m_gameState.m_currentProgress;
    if (tick == m_lastTick) return;

    // An attempt may start without a reset we could see (the first one, or
    // a respawn path that skips resetLevel): the tick counter starts over.
    bool freshStart = m_lastTick > tick || (!m_attemptPrepared && !m_attemptEnded);
    if (tick <= 2 && freshStart && this->canControl(layer)) {
        this->onAttemptStart(layer);
    }
    m_lastTick = tick;
    if (tick % 60 == 0) this->pollTraining();

    if (!m_attemptPrepared || m_attemptEnded || !m_config.enabled) {
        // Turned off mid-attempt: let go of the button and hand control back.
        if (m_pressed[0]) this->press(layer, 0, false);
        if (m_pressed[1]) this->press(layer, 1, false);
        if (!m_config.enabled) m_attemptPrepared = false;
        if (tick % 60 == 0) this->updateHud(layer);
        return;
    }

    layer->m_isTestMode = true;

    auto p1 = layer->m_player1;
    auto p2 = layer->m_player2;
    if (!p1 || p1->m_isDead) return;

    bool dual = layer->m_gameState.m_isDualMode && p2;
    bool twoPlayers = dual && layer->m_levelSettings && layer->m_levelSettings->m_twoPlayerMode;
    m_twoPlayers = twoPlayers;

    // Horizontal speed per tick, used to look ahead by the reaction time.
    PlayerObject* players[2] = {p1, p2};
    for (int p = 0; p < (dual ? 2 : 1); p++) {
        float x = players[p]->m_position.x;
        float dx = x - m_lastX[p];
        if (dx > 0.f && dx < 30.f) m_dx[p] = dx;
        m_lastX[p] = x;
    }

    // Keep replays of a known run exactly on it (see PlayerState).
    if (m_config.mode == LearnMode::Memory && m_memory.onBestPath()) {
        this->syncToRun(layer, tick, dual, m_bestStates);
    }
    else if (m_config.mode == LearnMode::Macro) {
        this->syncToRun(layer, tick, dual, m_macroStates);
    }

    uint8_t want = 0;
    if (m_config.mode == LearnMode::Macro) {
        want = tick < (int)m_macro.size() ? m_macro[tick] : 0;
    }
    else {
        if (tick % kTicksPerSecond == 0) m_sensors.prepare(layer);
        float inputs1[kInputs], inputs2[kInputs];
        int mode1 = modeOf(p1), mode2 = dual ? modeOf(p2) : (int)Cube;
        m_sensors.observe(p1, dual, inputs1);
        if (dual) m_sensors.observe(p2, dual, inputs2);

        if (m_config.mode == LearnMode::Memory) {
            float guide[2] = {m_skill.predict(mode1, inputs1), dual ? m_skill.predict(mode2, inputs2) : 0.f};
            // In a normal dual one button moves both icons: listen to both.
            if (dual && !twoPlayers) guide[0] = (guide[0] + guide[1]) * 0.5f;
            uint8_t idle = 0;
            if (clickIsIdle(p1, mode1, inputs1, m_runInputs, 1) && (!dual || twoPlayers || clickIsIdle(p2, mode2, inputs2, m_runInputs, 1))) {
                idle |= 1;
            }
            if (twoPlayers && clickIsIdle(p2, mode2, inputs2, m_runInputs, 2)) idle |= 2;
            want = m_memory.decide(tick, mode1, mode2, twoPlayers, guide, idle, m_rng);
        }
        else {
            want = this->decideHuman(layer, tick, dual, twoPlayers);
        }

        this->record(tick, 0, inputs1, mode1, want & 1);
        if (twoPlayers) this->record(tick, 1, inputs2, mode2, (want & 2) != 0);
    }

    this->recordStates(layer, tick, dual);

    while ((int)m_runInputs.size() < tick) {
        m_runInputs.push_back(m_runInputs.empty() ? 0 : m_runInputs.back());
    }
    if ((int)m_runInputs.size() == tick) m_runInputs.push_back(want);

    this->press(layer, 0, want & 1);
    if (twoPlayers) this->press(layer, 1, (want & 2) != 0);
    m_forceSync = false;

    m_attemptPercent = layer->getCurrentPercent();
    // At high speed many ticks pass per frame: refresh the text ~10x a second.
    double now = std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    if (now - m_lastHudUpdate > 0.1) {
        m_lastHudUpdate = now;
        this->updateHud(layer);
    }
}

uint8_t Bot::decideHuman(PlayLayer* layer, int tick, bool dual, bool twoPlayers) {
    int delay = m_config.reactionMs * kTicksPerSecond / 1000;
    int jitter = m_config.jitterMs * kTicksPerSecond / 1000;
    float lapse = m_config.lapsePercent / 100.f;

    // A person reacts to where they will be when the click lands.
    float inputs[kInputs];
    auto p1 = layer->m_player1;
    m_sensors.observe(p1, dual, inputs, m_dx[0] * delay);
    float out1 = m_skill.predict(modeOf(p1), inputs);
    float out2 = out1;
    if (dual) {
        auto p2 = layer->m_player2;
        m_sensors.observe(p2, dual, inputs, m_dx[1] * delay);
        out2 = m_skill.predict(modeOf(p2), inputs);
    }

    auto choose = [&](int player, float out) {
        bool want = out > m_threshold;
        if (tick < m_deviateUntil[player]) {
            want = !want;
        }
        else if (m_deviationRate > 0.f && std::uniform_real_distribution<float>(0.f, 1.f)(m_rng) < m_deviationRate) {
            // Trying something different here.
            m_deviateUntil[player] = tick + std::uniform_int_distribution<int>(2, 40)(m_rng);
            want = !want;
        }
        return want;
    };

    if (twoPlayers) {
        m_hands.want(0, choose(0, out1), tick, delay, jitter, lapse, m_rng);
        m_hands.want(1, choose(1, out2), tick, delay, jitter, lapse, m_rng);
    }
    else {
        float out = dual ? (out1 + out2) * 0.5f : out1;
        m_hands.want(0, choose(0, out), tick, delay, jitter, lapse, m_rng);
    }

    uint8_t result = m_hands.apply(0, tick) ? 1 : 0;
    if (twoPlayers && m_hands.apply(1, tick)) result |= 2;
    return result;
}

int Bot::learnFromRun(int from, int to, int every) {
    if (!m_brainLoaded) return 0;
    std::vector<Sample> batch;
    int kept = 0;
    for (int p = 0; p < (m_twoPlayers ? 2 : 1); p++) {
        auto const& run = m_runSamples[p];
        int end = std::min(to, (int)run.size());
        uint8_t bit = (uint8_t)(1 << p);
        for (int t = std::max(from, 0); t < end; t++) {
            auto const& sample = run[t];
            bool onGround = sample.extra[1] > 0.5f;
            if (!onGround && !clicksMatterInAir(sample.mode) && !orbInView(sample)) continue;

            // The moments around a press or release teach the most.
            bool nearSwitch = false;
            for (int d = -6; d <= 6 && !nearSwitch; d++) {
                int a = t + d;
                if (a >= 1 && a < (int)m_runInputs.size() && ((m_runInputs[a] ^ m_runInputs[a - 1]) & bit)) {
                    nearSwitch = true;
                }
            }
            if (!nearSwitch && t % 3 != 0) continue;
            if (kept++ % every != 0) continue;
            batch.push_back(sample);
        }
    }
    if (!batch.empty()) m_skill.addExperience(batch, m_rng);
    return (int)batch.size();
}

void Bot::scheduleTraining(int steps) {
    if (!m_brainLoaded || steps <= 0 || m_skill.experienceSize() == 0) return;
    if (m_training.valid()) {
        m_pendingTraining = std::min(m_pendingTraining + steps, 20000);
        return;
    }
    // Training runs on a copy in the background, so the game never freezes.
    unsigned seed = m_rng();
    m_training = std::async(std::launch::async, [copy = m_skill, seed, steps]() mutable {
        std::mt19937 rng(seed);
        copy.train(steps, rng);
        return std::move(copy);
    });
}

void Bot::pollTraining() {
    if (!m_training.valid()) return;
    if (m_training.wait_for(std::chrono::seconds(0)) != std::future_status::ready) return;
    m_skill.adoptTraining(m_training.get());
    if (m_pendingTraining > 0) {
        int steps = std::min(m_pendingTraining, 8000);
        m_pendingTraining = 0;
        this->scheduleTraining(steps);
    }
}

void Bot::onDeath(PlayLayer* layer) {
    if (!layer || layer != m_layer || !m_attemptPrepared || m_attemptEnded) return;
    m_attemptEnded = true;
    m_pressed[0] = m_pressed[1] = false;
    this->pollTraining();

    float percent = layer->getCurrentPercent();
    int unsafeFrom = m_lastTick - kUnsafeTicks;

    if (m_levelAttempts == 1 && m_config.mode != LearnMode::Macro) {
        m_lastEvent = fmt::format("First try: {:.1f}% (brain lv {})", percent, m_skill.brainLevel());
        this->logProgress("first try", percent);
    }

    switch (m_config.mode) {
        case LearnMode::Memory: {
            if (m_memory.onDeath(m_lastTick, percent)) {
                m_bestStates = m_runStates;
                m_lastEvent = fmt::format("New best: {:.1f}%", m_memory.bestPercent());
                if (m_config.learning && unsafeFrom > m_learnedUpTo) {
                    int added = this->learnFromRun(m_learnedUpTo, unsafeFrom, 1);
                    m_learnedUpTo = unsafeFrom;
                    this->scheduleTraining(std::min(4000, 500 + 3 * added));
                }
                this->saveMemory();
                this->logProgress("new best", percent);
            }
            else if (m_config.learning && m_bestStates.empty() && m_memory.onBestPath() && m_lastTick > 0) {
                // The remembered best was saved without exact positions (an
                // older version) and this replay of it drifted off and died
                // earlier: build on what can actually be repeated.
                m_memory.adoptCurrentAsBest(m_lastTick);
                m_bestStates = m_runStates;
                m_lastEvent = "Old record could not be replayed exactly - continuing from here";
                this->saveMemory();
            }
            else if (m_memory.attempts() % 25 == 0) {
                this->saveMemory();
            }
            break;
        }
        case LearnMode::Human: {
            if (!m_config.learning) {
                m_humanBest = std::max(m_humanBest, percent);
                break;
            }
            if (percent > m_humanBest) {
                m_humanBest = percent;
                m_stuckAttempts = 0;
                m_lastEvent = fmt::format("New best: {:.1f}%", percent);
                if (unsafeFrom > m_learnedUpTo) {
                    int added = this->learnFromRun(m_learnedUpTo, unsafeFrom, 1);
                    m_learnedUpTo = unsafeFrom;
                    this->scheduleTraining(std::min(3000, 500 + 3 * added));
                }
                this->logProgress("new best", percent);
            }
            else {
                m_stuckAttempts++;
                if (percent >= 0.7f * m_humanBest && unsafeFrom > 0) {
                    // A good run: practice what went right.
                    this->learnFromRun(0, unsafeFrom, 4);
                    this->scheduleTraining(200);
                }
                else {
                    this->scheduleTraining(100);
                }
            }
            break;
        }
        case LearnMode::Macro: {
            m_lastEvent = m_macro.empty()
                ? std::string("No macro for this level yet")
                : fmt::format("Macro lost sync at {:.1f}%", percent);
            break;
        }
    }
    this->updateHud(layer);
}

void Bot::onComplete(PlayLayer* layer) {
    if (!layer || layer != m_layer || !m_attemptPrepared || m_attemptEnded) return;
    m_attemptEnded = true;
    m_pressed[0] = m_pressed[1] = false;
    this->pollTraining();

    switch (m_config.mode) {
        case LearnMode::Memory: {
            if (!m_memory.completed() && m_config.learning) m_bestStates = m_runStates;
            m_memory.onComplete(m_lastTick);
            this->saveMemory();
            break;
        }
        case LearnMode::Human: {
            m_humanBest = 100.f;
            m_stuckAttempts = 0;
            break;
        }
        case LearnMode::Macro: {
            m_lastEvent = "Macro beat the level!";
            this->updateHud(layer);
            return;
        }
    }

    if (m_config.learning) {
        int added = this->learnFromRun(m_learnedUpTo, m_lastTick + 1, 1);
        m_learnedUpTo = m_lastTick + 1;
        this->scheduleTraining(std::min(8000, 2000 + 3 * added));
    }
    if (!m_beatenThisVisit) this->onFirstWin(layer);
    this->updateHud(layer);
}

void Bot::onFirstWin(PlayLayer* layer) {
    m_beatenThisVisit = true;
    bool newLevel = !m_skill.hasBeaten(m_levelKey);
    if (m_config.learning) m_skill.markLevelBeaten(m_levelKey);
    this->saveMacro(layer);
    this->saveBrain();
    this->logProgress("beaten", 100.f);

    m_lastEvent = fmt::format("LEVEL BEATEN in {} attempts! Macro saved", m_levelAttempts);
    Notification::create(
        fmt::format(
            "{} in {} attempts! Brain lv {}",
            newLevel ? "New level beaten" : "Beaten again",
            m_levelAttempts, m_skill.brainLevel()
        ),
        NotificationIcon::Success
    )->show();
}

void Bot::saveMacro(PlayLayer* layer) {
    if (m_runInputs.empty()) return;
    std::error_code ec;
    std::filesystem::create_directories(macroDir(), ec);

    // Keep one macro per level: drop the older file.
    auto suffix = fmt::format("[{}].json", m_levelKey);
    for (auto const& entry : std::filesystem::directory_iterator(macroDir(), ec)) {
        try {
            auto name = entry.path().filename().string();
            auto statesSuffix = suffix.substr(0, suffix.size() - 5) + ".states";
            if (name.ends_with(suffix) || name.ends_with(statesSuffix)) std::filesystem::remove(entry.path(), ec);
        }
        catch (...) {}
    }

    auto root = matjson::Value::object();
    root["format"] = "ai-bot-macro";
    root["version"] = 1;
    auto level = matjson::Value::object();
    level["id"] = layer->m_level ? layer->m_level->m_levelID.value() : 0;
    level["name"] = m_levelName;
    level["key"] = m_levelKey;
    root["level"] = level;
    root["ticksPerSecond"] = kTicksPerSecond;
    root["length"] = (int)m_runInputs.size();
    root["twoPlayers"] = m_twoPlayers;
    root["recordedBy"] = modeLabel(m_config.mode);
    root["attempts"] = m_levelAttempts;

    // Only the moments a button changes: [tick, player (1 or 2), down].
    auto inputs = matjson::Value::array();
    uint8_t previous = 0;
    for (int tick = 0; tick < (int)m_runInputs.size(); tick++) {
        uint8_t now = m_runInputs[tick];
        for (int p = 0; p < 2; p++) {
            uint8_t bit = (uint8_t)(1 << p);
            if ((now ^ previous) & bit) {
                inputs.push(matjson::Value(std::vector<matjson::Value>{
                    matjson::Value(tick), matjson::Value(p + 1), matjson::Value((now & bit) ? 1 : 0)
                }));
            }
        }
        previous = now;
    }
    root["inputs"] = inputs;

    auto fileName = fmt::format("{} {}", safeFileName(m_levelName), suffix);
    std::ofstream out(macroDir() / fileName, std::ios::trunc);
    out << root.dump(matjson::NO_INDENTATION);
    // The exact positions too, so the macro replays reliably (optional file).
    auto statesPath = macroDir() / fileName;
    writeStates(statesPath.replace_extension(".states"), m_runStates);
    if (out) {
        m_macroFile = fileName;
        m_macroKey.clear(); // reload on the next Macro attempt
    }
}

void Bot::loadMacro() {
    m_macro.clear();
    m_macroStates.clear();
    m_macroFile.clear();
    m_macroKey = m_levelKey;

    std::error_code ec;
    auto suffix = fmt::format("[{}].json", m_levelKey);
    for (auto const& entry : std::filesystem::directory_iterator(macroDir(), ec)) {
        std::string name;
        try {
            name = entry.path().filename().string();
        }
        catch (...) {
            continue;
        }
        if (!name.ends_with(suffix)) continue;

        std::ifstream in(entry.path());
        std::string text((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        auto parsed = matjson::parse(text);
        if (!parsed) continue;
        auto root = parsed.unwrap();

        int length = (int)root["length"].asInt().unwrapOr(0);
        auto events = root["inputs"].asArray();
        if (length <= 0 || length > 10'000'000 || !events) continue;

        m_macro.assign(length, 0);
        uint8_t state = 0;
        int last = 0;
        for (auto& event : events.unwrap()) {
            int tick = std::clamp((int)event[0].asInt().unwrapOr(0), 0, length);
            int player = (int)event[1].asInt().unwrapOr(1);
            bool down = event[2].asInt().unwrapOr(0) != 0;
            if (tick > last) {
                std::fill(m_macro.begin() + last, m_macro.begin() + tick, state);
                last = tick;
            }
            uint8_t bit = (uint8_t)(player == 2 ? 2 : 1);
            state = down ? (state | bit) : (state & ~bit);
        }
        std::fill(m_macro.begin() + last, m_macro.end(), state);
        m_macroFile = name;
        auto statesPath = entry.path();
        m_macroStates = readStates(statesPath.replace_extension(".states"));
        return;
    }
}

void Bot::logProgress(char const* event, float percent) {
    std::error_code ec;
    std::filesystem::create_directories(saveDir(), ec);
    auto path = saveDir() / "progress.csv";
    bool fresh = !std::filesystem::exists(path, ec);
    std::ofstream out(path, std::ios::app);
    if (!out) return;
    if (fresh) out << "time (UTC),level,mode,event,attempt,percent,brain level,levels beaten,moves learned\n";

    std::string name = m_levelName;
    std::replace(name.begin(), name.end(), '"', '\'');
    auto now = std::chrono::floor<std::chrono::seconds>(std::chrono::system_clock::now());
    out << fmt::format(
        "{:%Y-%m-%d %H:%M:%S},\"{}\",{},{},{},{:.1f},{},{},{}\n",
        now, name, modeLabel(m_config.mode), event, m_levelAttempts, percent,
        m_skill.brainLevel(), m_skill.levelsBeaten(), m_skill.movesLearned()
    );
}

void Bot::ensureBrain() {
    if (m_brainLoaded) return;
    if (!m_skill.load(saveDir())) {
        m_skill.reset(m_rng);
    }
    MemoryLearner::loadFixStats(saveDir() / "fixes.bin");
    m_brainLoaded = true;
}

void Bot::saveBrain() {
    if (!m_brainLoaded) return;
    m_skill.save(saveDir());
    MemoryLearner::saveFixStats(saveDir() / "fixes.bin");
}

void Bot::saveMemory() {
    if (!m_levelKey.empty() && m_memory.attempts() > 0) {
        m_memory.save(this->memoryPath());
        this->saveStates();
    }
}

namespace {
    constexpr char kStatesMagic[8] = {'G', 'D', 'A', 'I', 'S', 'T', 'A', '1'};
}

void Bot::writeStates(std::filesystem::path const& path, std::vector<TickState> const& states) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return;
    uint32_t count = (uint32_t)states.size();
    out.write(kStatesMagic, sizeof(kStatesMagic));
    out.write(reinterpret_cast<char const*>(&count), sizeof(count));
    out.write(reinterpret_cast<char const*>(states.data()), (std::streamsize)count * sizeof(TickState));
}

std::vector<Bot::TickState> Bot::readStates(std::filesystem::path const& path) {
    std::ifstream in(path, std::ios::binary);
    char magic[8];
    uint32_t count;
    if (!in || !in.read(magic, sizeof(magic)) || std::memcmp(magic, kStatesMagic, sizeof(magic)) != 0) return {};
    if (!in.read(reinterpret_cast<char*>(&count), sizeof(count)) || count > 10'000'000) return {};
    std::vector<TickState> states(count);
    if (!in.read(reinterpret_cast<char*>(states.data()), (std::streamsize)count * sizeof(TickState))) return {};
    return states;
}

void Bot::saveStates() const {
    auto path = this->memoryPath();
    writeStates(path.replace_extension(".states"), m_bestStates);
}

void Bot::loadStates() {
    auto path = this->memoryPath();
    m_bestStates = readStates(path.replace_extension(".states"));
}

void Bot::recordStates(PlayLayer* layer, int tick, bool dual) {
    TickState state{};
    PlayerObject* players[2] = {layer->m_player1, layer->m_player2};
    for (int p = 0; p < (dual ? 2 : 1); p++) {
        auto player = players[p];
        state[p] = {player->m_position.x, player->m_position.y, player->getRotation(), player->m_yVelocity};
    }
    while ((int)m_runStates.size() < tick) m_runStates.push_back(state);
    if ((int)m_runStates.size() == tick) m_runStates.push_back(state);
}

void Bot::syncToRun(PlayLayer* layer, int tick, bool dual, std::vector<TickState> const& run) {
    if (tick >= (int)run.size()) return;
    PlayerObject* players[2] = {layer->m_player1, layer->m_player2};
    for (int p = 0; p < (dual ? 2 : 1); p++) {
        auto player = players[p];
        auto const& want = run[tick][p];
        float dx = std::abs(player->m_position.x - want.x);
        float dy = std::abs(player->m_position.y - want.y);
        double dv = std::abs(player->m_yVelocity - want.yVelocity);
        if (dx < 0.001f && dy < 0.001f && dv < 1e-6) continue;
        // A big difference is not drift (another start, a changed level).
        if (dx + dy > 60.f) continue;
        auto position = CCPoint(want.x, want.y);
        player->m_position = position;
        player->setPosition(position);
        player->setRotation(want.rotation);
        player->m_yVelocity = want.yVelocity;
        m_syncFixes++;
    }
}

void Bot::resetLevelMemory() {
    m_memory.clear();
    m_learnedUpTo = 0;
    m_humanBest = 0.f;
    m_stuckAttempts = 0;
    if (!m_levelKey.empty()) {
        std::error_code ec;
        std::filesystem::remove(this->memoryPath(), ec);
        auto states = this->memoryPath();
        std::filesystem::remove(states.replace_extension(".states"), ec);
    }
    m_bestStates.clear();
    // The current attempt was built on the old memory.
    if (m_config.mode == LearnMode::Memory) m_attemptPrepared = false;
    m_lastEvent = "Level memory erased";
    if (m_layer) this->updateHud(m_layer);
}

void Bot::resetBrain() {
    // Throw away any training still running on the old brain.
    if (m_training.valid()) m_training.get();
    m_pendingTraining = 0;
    m_skill.reset(m_rng);
    m_brainLoaded = true;
    m_learnedUpTo = 0;
    m_humanBest = 0.f;
    m_stuckAttempts = 0;
    std::error_code ec;
    std::filesystem::remove(saveDir() / "skill.bin", ec);
    std::filesystem::remove(saveDir() / "experience.bin", ec);
    std::filesystem::remove(saveDir() / "fixes.bin", ec);
    MemoryLearner::resetFixStats();
    if (m_config.mode != LearnMode::Macro) m_attemptPrepared = false;
    m_lastEvent = "Brain reset";
    if (m_layer) this->updateHud(m_layer);
}

void Bot::openFolder() {
    std::error_code ec;
    std::filesystem::create_directories(macroDir(), ec);
    geode::utils::file::openFolder(saveDir());
}

bool Bot::speedBoosted(PlayLayer* layer) const {
    return layer && layer == m_layer && m_config.enabled && m_config.speed > 1.f;
}

void Bot::reportPhysics(double milliseconds, float simulated, float requested) {
    // How many ticks this PC simulates per millisecond, smoothed.
    double ticks = simulated * kTicksPerSecond;
    if (milliseconds > 0.05 && ticks >= 1.0) {
        double rate = ticks / milliseconds;
        m_ticksPerMs = m_ticksPerMs <= 0.0 ? rate : m_ticksPerMs * 0.9 + rate * 0.1;
    }
    // Spend at most ~25 ms of each frame on physics.
    if (m_ticksPerMs > 0.0) {
        m_budgetTicks = (float)std::clamp(m_ticksPerMs * 25.0, 4.0, 200000.0);
    }
    // Real speed: game seconds simulated per real second.
    float scale = CCDirector::get()->getScheduler()->getTimeScale();
    float realDt = scale > 0.f ? requested / scale : requested;
    if (realDt > 0.f) {
        m_realSpeed = m_realSpeed * 0.9f + 0.1f * (simulated / realDt);
    }
}

void Bot::applySpeed() {
    static bool s_applied = false;
    bool want = m_layer && m_config.enabled && m_config.speed != 1.f;
    auto scheduler = CCDirector::get()->getScheduler();
    if (want) {
        scheduler->setTimeScale(m_config.speed);
        s_applied = true;
    }
    else if (s_applied) {
        // Only undo our own change, so other speed mods keep working.
        scheduler->setTimeScale(1.f);
        s_applied = false;
    }
}

std::string Bot::statusText() const {
    if (!m_config.enabled) return "AI Bot: OFF";

    std::string text = fmt::format(
        "AI Bot - {}{}",
        modeLabel(m_config.mode),
        m_config.mode == LearnMode::Macro ? "" : (m_config.learning ? " (learning)" : " (showing)")
    );
    if (m_config.speed != 1.f) {
        text += fmt::format("  x{:g}", m_config.speed);
        if (m_config.speed > 1.f && m_layer) text += fmt::format(" (real x{:.0f})", m_realSpeed);
    }

    if (m_brainLoaded && m_config.mode != LearnMode::Macro) {
        text += fmt::format(
            "\nBrain lv {} | {} levels beaten | {} moves | acc {:.0f}%{}",
            m_skill.brainLevel(), m_skill.levelsBeaten(), m_skill.movesLearned(),
            m_skill.accuracy() * 100.f, m_training.valid() ? " | thinking..." : ""
        );
    }

    if (m_layer) {
        if (m_layer->m_isPlatformer) return text + "\nPlatformer levels are not supported";
        if (m_layer->m_isPracticeMode) return text + "\nPaused: turn off practice mode";
        if (!m_attemptPrepared && !m_attemptEnded) return text + "\nStarts on the next attempt (restart)";
    }

    switch (m_config.mode) {
        case LearnMode::Memory: {
            if (m_levelKey.empty()) {
                text += "\nEnter a level to start";
                break;
            }
            text += fmt::format(
                "\nAttempt {} | Best {:.1f}% | Now {:.1f}%",
                m_memory.attempts(), m_memory.bestPercent(), m_attemptPercent
            );
            if (m_syncFixes > 0) text += fmt::format(" | sync fixes {}", m_syncFixes);
            if (m_memory.completed()) {
                text += "\nLevel beaten - replaying the winning run";
            }
            else if (m_config.learning && m_memory.attempts() > 0) {
                if (auto idea = m_memory.currentIdea()) {
                    text += fmt::format("\nDeaths at this spot: {} | fixing the mistake: {}", m_memory.deathsAtSpot(), idea);
                }
                else if (m_memory.exploring()) {
                    text += m_memory.guided() ? "\nTrying what the brain suggests" : "\nTrying bolder new moves";
                }
            }
            break;
        }
        case LearnMode::Human: {
            text += fmt::format(
                "\nAttempt {} | Best {:.1f}% | Now {:.1f}%",
                m_levelAttempts, m_humanBest, m_attemptPercent
            );
            break;
        }
        case LearnMode::Macro: {
            if (m_layer && m_macroKey == m_levelKey) {
                text += m_macro.empty()
                    ? "\nNo macro for this level yet - beat it in Memory or Human mode"
                    : fmt::format("\nPlaying: {}", m_macroFile);
            }
            break;
        }
    }

    if (!m_lastEvent.empty()) text += "\n" + m_lastEvent;
    return text;
}

void Bot::updateHud(PlayLayer* layer) {
    if (!m_hud || layer != m_layer) return;
    m_hud->setVisible(m_config.showHud && m_config.enabled);
    if (m_hud->isVisible()) m_hud->setString(this->statusText().c_str());
}
