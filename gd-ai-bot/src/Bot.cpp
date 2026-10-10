#include "Bot.hpp"

#include <Geode/Geode.hpp>

#include <algorithm>

using namespace geode::prelude;
using namespace aibot;

namespace {
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

    std::filesystem::path brainPath() {
        return Mod::get()->getSaveDir() / "brain.bin";
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
    m_config.mode = mod->getSettingValue<std::string>("mode") == "Human" ? LearnMode::Human : LearnMode::Memory;
    m_config.learning = mod->getSettingValue<bool>("learning");
    m_config.speed = (float)mod->getSettingValue<double>("speed");
    m_config.reactionMs = (int)mod->getSettingValue<int64_t>("reaction-ms");
    m_config.jitterMs = (int)mod->getSettingValue<int64_t>("jitter-ms");
    m_config.lapsePercent = (float)mod->getSettingValue<double>("lapse-percent");
    m_config.population = (int)mod->getSettingValue<int64_t>("population");
    m_config.mutationRate = (float)mod->getSettingValue<double>("mutation-rate");
    m_config.showHud = mod->getSettingValue<bool>("show-hud");
}

std::filesystem::path Bot::memoryPath() const {
    return Mod::get()->getSaveDir() / "memory" / (m_levelKey + ".bin");
}

bool Bot::canControl(PlayLayer* layer) const {
    return m_config.enabled && layer && !layer->m_isPracticeMode && !layer->m_isPlatformer;
}

bool Bot::isPlaying(PlayLayer* layer) const {
    return layer && layer == m_layer && m_config.enabled && m_attemptPrepared && !m_attemptEnded;
}

void Bot::detach() {
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

    auto key = levelKeyFor(layer);
    if (key != m_levelKey) {
        this->saveMemory();
        m_levelKey = key;
        m_memory.load(this->memoryPath());
    }

    m_attemptEnded = false;
    m_lastTick = -1;
    m_attemptPercent = 0.f;
    m_pressed[0] = m_pressed[1] = false;
    m_forceSync = true;

    m_attemptPrepared = this->canControl(layer);
    if (m_attemptPrepared) m_usedThisLevel = true;
    // Once the bot has played here, nothing until leaving the level counts
    // as the player's own progress (like playing from a start position).
    if (m_usedThisLevel) layer->m_isTestMode = true;
    if (m_attemptPrepared) {
        if (m_config.mode == LearnMode::Memory) {
            m_memory.beginAttempt(m_config.learning, m_rng);
        }
        else {
            this->ensureBrain();
            m_hands.reset();
            m_sensors.prepare(layer);
            m_humanAttempts++;
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

    uint8_t want;
    if (m_config.mode == LearnMode::Memory) {
        want = m_memory.decide(tick, modeOf(p1), dual ? modeOf(p2) : (int)Cube, twoPlayers, m_rng);
    }
    else {
        want = this->decideHuman(layer, tick, dual, twoPlayers);
    }

    this->press(layer, 0, want & 1);
    if (twoPlayers) this->press(layer, 1, (want & 2) != 0);
    m_forceSync = false;

    m_attemptPercent = layer->getCurrentPercent();
    if (tick % 24 == 0) this->updateHud(layer);
}

uint8_t Bot::decideHuman(PlayLayer* layer, int tick, bool dual, bool twoPlayers) {
    if (tick % kTicksPerSecond == 0) m_sensors.prepare(layer);

    auto const& genome = m_config.learning ? m_population.current() : m_population.champion();
    int delay = m_config.reactionMs * kTicksPerSecond / 1000;
    int jitter = m_config.jitterMs * kTicksPerSecond / 1000;
    float lapse = m_config.lapsePercent / 100.f;

    float inputs[kInputs];
    auto p1 = layer->m_player1;
    m_sensors.observe(p1, m_hands.wanted(0), dual, inputs);
    float out1 = evaluate(genome, modeOf(p1), inputs);
    float out2 = out1;
    if (dual) {
        auto p2 = layer->m_player2;
        m_sensors.observe(p2, m_hands.wanted(twoPlayers ? 1 : 0), dual, inputs);
        out2 = evaluate(genome, modeOf(p2), inputs);
    }

    if (twoPlayers) {
        m_hands.want(0, out1 > 0.5f, tick, delay, jitter, lapse, m_rng);
        m_hands.want(1, out2 > 0.5f, tick, delay, jitter, lapse, m_rng);
    }
    else {
        // One button moves both icons in a normal dual: listen to both.
        float out = dual ? (out1 + out2) * 0.5f : out1;
        m_hands.want(0, out > 0.5f, tick, delay, jitter, lapse, m_rng);
    }

    uint8_t result = m_hands.apply(0, tick) ? 1 : 0;
    if (twoPlayers && m_hands.apply(1, tick)) result |= 2;
    return result;
}

void Bot::onDeath(PlayLayer* layer) {
    if (!layer || layer != m_layer || !m_attemptPrepared || m_attemptEnded) return;
    m_attemptEnded = true;
    m_pressed[0] = m_pressed[1] = false;

    float percent = layer->getCurrentPercent();
    if (m_config.mode == LearnMode::Memory) {
        if (m_memory.onDeath(m_lastTick, percent)) {
            m_lastEvent = fmt::format("New best: {:.1f}%", m_memory.bestPercent());
            this->saveMemory();
        }
        else if (m_memory.attempts() % 25 == 0) {
            this->saveMemory();
        }
    }
    else {
        if (percent > m_humanBestPercent) {
            m_humanBestPercent = percent;
            m_lastEvent = fmt::format("New best: {:.1f}%", percent);
        }
        if (m_config.learning &&
            m_population.report(percent, m_config.population, m_config.mutationRate, m_rng)) {
            m_lastEvent = fmt::format("Generation {} born", m_population.generation());
            this->saveBrain();
        }
    }
    this->updateHud(layer);
}

void Bot::onComplete(PlayLayer* layer) {
    if (!layer || layer != m_layer || !m_attemptPrepared || m_attemptEnded) return;
    m_attemptEnded = true;
    m_pressed[0] = m_pressed[1] = false;

    if (m_config.mode == LearnMode::Memory) {
        m_memory.onComplete(m_lastTick);
        this->saveMemory();
    }
    else {
        m_humanBestPercent = 100.f;
        if (m_config.learning) {
            // Beating the level is worth more than any death.
            m_population.report(110.f, m_config.population, m_config.mutationRate, m_rng);
        }
        this->saveBrain();
    }
    m_lastEvent = "LEVEL COMPLETE!";
    this->updateHud(layer);
}

void Bot::ensureBrain() {
    if (m_brainLoaded) return;
    if (!m_population.load(brainPath())) {
        m_population.reset(m_config.population, m_rng);
    }
    m_brainLoaded = true;
}

void Bot::saveBrain() {
    if (m_brainLoaded) m_population.save(brainPath());
}

void Bot::saveMemory() {
    if (!m_levelKey.empty() && m_memory.attempts() > 0) {
        m_memory.save(this->memoryPath());
    }
}

void Bot::resetLevelMemory() {
    m_memory.clear();
    if (!m_levelKey.empty()) {
        std::error_code ec;
        std::filesystem::remove(this->memoryPath(), ec);
    }
    // The current attempt was built on the old memory.
    if (m_config.mode == LearnMode::Memory) m_attemptPrepared = false;
    m_lastEvent = "Level memory erased";
    if (m_layer) this->updateHud(m_layer);
}

void Bot::resetBrain() {
    this->reloadConfig();
    m_population.reset(m_config.population, m_rng);
    m_brainLoaded = true;
    m_humanBestPercent = 0.f;
    std::error_code ec;
    std::filesystem::remove(brainPath(), ec);
    if (m_config.mode == LearnMode::Human) m_attemptPrepared = false;
    m_lastEvent = "Brain reset";
    if (m_layer) this->updateHud(m_layer);
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
        m_config.mode == LearnMode::Memory ? "Memory" : "Human",
        m_config.learning ? " (learning)" : " (showing)"
    );
    if (m_config.speed != 1.f) text += fmt::format("  x{:.2f}", m_config.speed);

    if (m_layer) {
        if (m_layer->m_isPlatformer) return text + "\nPlatformer levels are not supported";
        if (m_layer->m_isPracticeMode) return text + "\nPaused: turn off practice mode";
        if (!m_attemptPrepared && !m_attemptEnded) return text + "\nStarts on the next attempt (restart)";
    }

    if (m_config.mode == LearnMode::Memory) {
        if (m_levelKey.empty()) {
            text += "\nEnter a level to start";
        }
        else {
            text += fmt::format(
                "\nAttempt {} | Best {:.1f}% | Now {:.1f}%",
                m_memory.attempts(), m_memory.bestPercent(), m_attemptPercent
            );
            if (m_memory.completed()) {
                text += "\nLevel beaten - replaying the winning run";
            }
            else if (m_config.learning && m_memory.attempts() > 0) {
                float back = (m_memory.bestTick() - m_memory.branchTick()) / (float)kTicksPerSecond;
                text += fmt::format("\nTrying new moves {:.2f}s before the furthest death", std::max(0.f, back));
            }
        }
    }
    else {
        if (!m_brainLoaded) {
            text += "\nBrain will load in a level";
        }
        else {
            text += fmt::format(
                "\nGen {} | Brain {}/{} | Best {:.1f}% | Now {:.1f}%",
                m_population.generation(), m_population.index() + 1, m_population.size(),
                m_humanBestPercent, m_attemptPercent
            );
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
