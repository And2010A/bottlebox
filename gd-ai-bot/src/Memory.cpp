#include "Memory.hpp"
#include "Common.hpp"

#include <algorithm>
#include <cmath>
#include <climits>
#include <cstring>
#include <fstream>
#include <unordered_map>

using namespace aibot;

namespace {
    constexpr char kMagicV1[8] = {'G', 'D', 'A', 'I', 'M', 'E', 'M', '1'};
    constexpr char kMagicV2[8] = {'G', 'D', 'A', 'I', 'M', 'E', 'M', '2'};
    constexpr uint64_t kHashSeed = 0x9E3779B97F4A7C15ull;
    // How far back (in ticks) from the furthest death a random try starts,
    // once every planned fix has failed.
    constexpr int kBaseBackoff = 48;
    // After this many failures at the same frontier, look further back.
    constexpr int kFailsBeforeWidening = 8;
    // While following the brain, how often to try something else instead.
    constexpr float kDeviationPerTick = 1.f / 300.f;
    // Presses that started this long before a death may have caused it.
    constexpr int kBlameWindow = 160;
    // Dying less than this much further than before is still the same spot.
    constexpr int kSameSpotTicks = 30;

    uint64_t mix(uint64_t hash, uint8_t value) {
        hash ^= value + 0x9E3779B97F4A7C15ull + (hash << 6) + (hash >> 2);
        hash *= 0xBF58476D1CE4E5B9ull;
        return hash ^ (hash >> 31);
    }

    struct HoldRange {
        int pressMin, pressMax, releaseMin, releaseMax;
    };

    // The "base knowledge" of each mode: how long a sensible press or pause
    // lasts there, in ticks.
    HoldRange holdRange(int mode) {
        switch (mode) {
            case Ship:
            case Swing: return {3, 70, 3, 70};
            case Wave: return {2, 50, 2, 50};
            case Ball:
            case Spider: return {1, 6, 10, 150};
            case Ufo: return {1, 6, 6, 60};
            case Robot: return {1, 40, 8, 120};
            case Cube:
            default: return {1, 12, 8, 120};
        }
    }

    // A typical single press (or short release) in each mode.
    int typicalPress(int mode) {
        switch (mode) {
            case Ship:
            case Swing: return 16;
            case Wave: return 12;
            case Robot: return 10;
            default: return 3;
        }
    }

    // Modes where how long you hold matters, not just when you press.
    bool holdMatters(int mode) {
        return mode == Ship || mode == Swing || mode == Wave || mode == Robot;
    }

    int sampleDuration(int mode, bool pressing, std::mt19937& rng) {
        auto range = holdRange(mode);
        int lo = pressing ? range.pressMin : range.releaseMin;
        int hi = pressing ? range.pressMax : range.releaseMax;
        // Log-uniform, so short taps and long holds are both common.
        std::uniform_real_distribution<float> dist(std::log((float)lo), std::log((float)hi + 1.f));
        return std::max(1, (int)std::exp(dist(rng)));
    }

    struct Press {
        int start, end; // [start, end)
    };

    std::vector<Press> pressesOf(std::vector<uint8_t> const& run, int length, uint8_t bit) {
        std::vector<Press> presses;
        int start = -1;
        for (int t = 0; t < length; t++) {
            bool held = (run[t] & bit) != 0;
            if (held && start < 0) start = t;
            if (!held && start >= 0) {
                presses.push_back({start, t});
                start = -1;
            }
        }
        if (start >= 0) presses.push_back({start, length});
        return presses;
    }

    void setRange(std::vector<uint8_t>& run, int from, int to, uint8_t bit, bool held) {
        from = std::max(from, 0);
        to = std::min(to, (int)run.size());
        for (int t = from; t < to; t++) {
            run[t] = held ? (run[t] | bit) : (run[t] & ~bit);
        }
    }

    template <class T>
    void write(std::ofstream& out, T const& value) {
        out.write(reinterpret_cast<char const*>(&value), sizeof(T));
    }

    template <class T>
    bool read(std::ifstream& in, T& value) {
        return static_cast<bool>(in.read(reinterpret_cast<char*>(&value), sizeof(T)));
    }
}

namespace {
    constexpr char kStatsMagic[8] = {'G', 'D', 'A', 'I', 'F', 'I', 'X', '1'};
    // Wins per (mode, fix key). Keys stay within +-1000.
    std::unordered_map<int32_t, uint32_t> s_fixWins;

    int32_t statsKey(int situation, int key) {
        return situation * 4096 + key + 2048;
    }

    int16_t fixKey(int kind, int amount) {
        return (int16_t)(kind * 400 + std::clamp(amount, -199, 199));
    }
}

bool MemoryLearner::loadFixStats(std::filesystem::path const& path) {
    s_fixWins.clear();
    std::ifstream in(path, std::ios::binary);
    char magic[8];
    uint32_t count;
    if (!in || !in.read(magic, sizeof(magic)) || std::memcmp(magic, kStatsMagic, sizeof(magic)) != 0) return false;
    if (!read(in, count) || count > 100'000) return false;
    for (uint32_t i = 0; i < count; i++) {
        int32_t key;
        uint32_t wins;
        if (!read(in, key) || !read(in, wins)) return false;
        s_fixWins[key] = wins;
    }
    return true;
}

bool MemoryLearner::saveFixStats(std::filesystem::path const& path) {
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return false;
    out.write(kStatsMagic, sizeof(kStatsMagic));
    write(out, (uint32_t)s_fixWins.size());
    for (auto const& [key, wins] : s_fixWins) {
        write(out, key);
        write(out, wins);
    }
    return static_cast<bool>(out);
}

void MemoryLearner::resetFixStats() {
    s_fixWins.clear();
}

void MemoryLearner::clear() {
    *this = MemoryLearner();
}

bool MemoryLearner::load(std::filesystem::path const& path) {
    this->clear();
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;

    char magic[8];
    if (!in.read(magic, sizeof(magic))) return false;
    bool v2 = std::memcmp(magic, kMagicV2, sizeof(magic)) == 0;
    if (!v2 && std::memcmp(magic, kMagicV1, sizeof(magic)) != 0) return false;

    int32_t bestTick, attempts;
    float bestPercent;
    uint8_t completed;
    uint32_t size;
    if (!read(in, bestTick) || !read(in, bestPercent) || !read(in, completed) || !read(in, attempts) || !read(in, size)) {
        return false;
    }
    if (size > 100'000'000) return false;

    std::vector<Input> best(size);
    if (size && !in.read(reinterpret_cast<char*>(best.data()), size)) return false;

    std::vector<uint8_t> modes;
    if (v2) {
        uint32_t modeCount;
        if (!read(in, modeCount) || modeCount > 100'000'000) return false;
        modes.resize(modeCount);
        if (modeCount && !in.read(reinterpret_cast<char*>(modes.data()), modeCount)) return false;
    }

    m_best = std::move(best);
    m_bestModes = std::move(modes);
    m_bestTick = bestTick;
    m_bestPercent = bestPercent;
    m_completed = completed != 0;
    m_attempts = attempts;
    if (!m_completed && !m_best.empty()) this->planFixes(m_bestTick);
    return true;
}

bool MemoryLearner::save(std::filesystem::path const& path) const {
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return false;

    out.write(kMagicV2, sizeof(kMagicV2));
    write(out, (int32_t)m_bestTick);
    write(out, m_bestPercent);
    write(out, (uint8_t)m_completed);
    write(out, (int32_t)m_attempts);
    write(out, (uint32_t)m_best.size());
    out.write(reinterpret_cast<char const*>(m_best.data()), m_best.size());
    write(out, (uint32_t)m_bestModes.size());
    out.write(reinterpret_cast<char const*>(m_bestModes.data()), m_bestModes.size());
    return static_cast<bool>(out);
}

void MemoryLearner::planFixes(int deathTick) {
    m_fixes.clear();
    m_nextFix = 0;
    m_triedPlans.clear();

    int length = std::min(deathTick, (int)m_best.size());
    if (length <= 0) return;

    std::vector<Fix> perPlayer[2];
    for (int p = 0; p < (m_twoPlayers ? 2 : 1); p++) {
        uint8_t bit = (uint8_t)(1 << p);
        auto presses = pressesOf(m_best, length, bit);
        int mode = length - 1 < (int)m_bestModes.size() ? (m_bestModes[length - 1] >> (p * 4)) & 0xF : (int)Cube;
        int press = typicalPress(mode);
        bool holds = holdMatters(mode);

        // The presses that could have caused this death, latest first.
        std::vector<int> recent;
        for (int i = (int)presses.size() - 1; i >= 0 && recent.size() < 3; i--) {
            if (presses[i].start >= length - kBlameWindow) recent.push_back(i);
        }
        int gap = recent.empty() ? INT_MAX : length - presses[recent.front()].end;
        // Holding a cube's button makes it jump again on every landing, so
        // when it held long, when to let go matters too.
        for (int r : recent) {
            if (presses[r].end - presses[r].start >= 12) holds = true;
        }

        auto& fixes = perPlayer[p];
        // The situation: was there a press shortly before dying? Fixes are
        // remembered per situation, since each needs different ones.
        uint8_t situation = (uint8_t)(mode | ((gap > 60 ? 1 : 0) << 4));
        auto add = [&](Fix::Kind kind, int tick, int amount, int key) {
            fixes.push_back({kind, (uint8_t)p, tick, amount, situation, fixKey(kind, key)});
        };
        // A new press (or a short release while holding) `d` ticks before the death.
        auto toggles = [&](std::initializer_list<int> distances) {
            for (int d : distances) add(Fix::Toggle, length - d, press, d);
        };
        auto shifts = [&](std::initializer_list<int> amounts, size_t count) {
            for (int s : amounts) {
                for (size_t r = 0; r < std::min(count, recent.size()); r++) {
                    // The key also tells which press it was (latest = 0).
                    int which = (int)r * 60;
                    add(Fix::Shift, recent[r], -s, which - s);
                    add(Fix::Shift, recent[r], s, which + s);
                    if (holds) {
                        add(Fix::Resize, recent[r], s, which + s);
                        add(Fix::Resize, recent[r], -s, which - s);
                    }
                }
            }
        };

        // Most likely fixes first. No press for a while before dying usually
        // means a jump was missing; a press just before means its timing.
        if (gap > 60) toggles({40, 30, 50});
        shifts({6, 12}, 2);
        if (gap <= 60) toggles({40, 30, 50});
        toggles({20, 60});
        for (size_t r = 0; r < std::min<size_t>(2, recent.size()); r++) {
            auto const& skipped = presses[recent[r]];
            fixes.push_back({Fix::Toggle, (uint8_t)p, skipped.start, skipped.end - skipped.start, situation,
                fixKey(Fix::Toggle, -1 - (int)r)});
        }
        shifts({3, 18, 26}, 3);
        toggles({12, 70, 85});
        shifts({36, 50}, 3);
        toggles({100, 120, 140});

        // Then let experience reorder them: fixes that worked before in this
        // mode go first.
        std::stable_sort(fixes.begin(), fixes.end(), [](Fix const& a, Fix const& b) {
            auto wins = [](Fix const& f) {
                auto it = s_fixWins.find(statsKey(f.situation, f.key));
                return it == s_fixWins.end() ? 0u : it->second;
            };
            return wins(a) > wins(b);
        });
    }

    // Two players: alternate between their ideas.
    for (size_t i = 0; i < std::max(perPlayer[0].size(), perPlayer[1].size()); i++) {
        for (auto const& list : perPlayer) {
            if (i < list.size()) m_fixes.push_back(list[i]);
        }
    }
}

bool MemoryLearner::buildPlan(Fix const& fix, std::vector<Input>& plan) const {
    int length = std::min(m_bestTick, (int)m_best.size());
    if (length <= 0) return false;
    plan.assign(m_best.begin(), m_best.begin() + length);

    uint8_t bit = (uint8_t)(1 << fix.player);
    if (fix.kind == Fix::Toggle) {
        if (fix.tick < 0 || fix.tick >= length || fix.amount <= 0) return false;
        for (int t = fix.tick; t < std::min(length, fix.tick + fix.amount); t++) plan[t] ^= bit;
        return true;
    }

    auto presses = pressesOf(m_best, length, bit);
    if (fix.tick < 0 || fix.tick >= (int)presses.size()) return false;
    auto press = presses[fix.tick];
    int previousEnd = fix.tick > 0 ? presses[fix.tick - 1].end : -1;
    int nextStart = fix.tick + 1 < (int)presses.size() ? presses[fix.tick + 1].start : INT_MAX;
    bool heldAtDeath = press.end >= length;

    int start = press.start, end = press.end;
    if (fix.kind == Fix::Shift) {
        start += fix.amount;
        if (!heldAtDeath) end += fix.amount;
    }
    else {
        if (heldAtDeath && fix.amount > 0) return false;
        end += fix.amount;
    }
    // Keep at least one released tick between presses, and stay in range.
    if (start < 0 || end <= start || start <= previousEnd || end >= nextStart || start >= length) return false;

    setRange(plan, press.start, press.end, bit, false);
    setRange(plan, start, end, bit, true);
    return true;
}

void MemoryLearner::beginAttempt(bool learning, std::mt19937& rng) {
    m_learning = learning;
    m_current.clear();
    m_currentModes.clear();
    m_hash = kHashSeed;
    m_exploring = false;
    m_state = 0;
    m_usingPlan = false;
    m_offBestPath = false;
    m_idea = nullptr;
    if (m_backoff <= 0) m_backoff = kBaseBackoff;

    if (!learning || m_completed) {
        // Just show what is known.
        m_branch = INT_MAX;
    }
    else if (m_best.empty()) {
        m_branch = 0;
    }
    else {
        // Test the next idea for fixing the last death.
        while (m_nextFix < m_fixes.size() && !m_usingPlan) {
            auto const& fix = m_fixes[m_nextFix++];
            if (!this->buildPlan(fix, m_plan)) continue;
            uint64_t hash = kHashSeed;
            for (auto input : m_plan) hash = mix(hash, input);
            if (!m_triedPlans.insert(hash).second) continue;

            m_usingPlan = true;
            m_activeFix = fix;
            uint8_t bit = (uint8_t)(1 << fix.player);
            switch (fix.kind) {
                case Fix::Shift: m_idea = fix.amount < 0 ? "jump earlier" : "jump later"; break;
                case Fix::Resize: m_idea = fix.amount > 0 ? "hold longer" : "hold shorter"; break;
                case Fix::Toggle: {
                    bool wasHeld = fix.tick < (int)m_best.size() && (m_best[fix.tick] & bit);
                    bool wholePress = wasHeld && (fix.tick == 0 || !(m_best[fix.tick - 1] & bit));
                    m_idea = !wasHeld ? "add a jump" : wholePress ? "skip a jump" : "let go for a moment";
                    break;
                }
            }
        }

        if (m_usingPlan) {
            m_branch = INT_MAX;
        }
        else {
            // Every planned idea failed: search more freely further back.
            int lo = std::max(0, m_bestTick - m_backoff);
            int hi = std::max(lo, m_bestTick - 1);
            m_branch = std::uniform_int_distribution<int>(lo, hi)(rng);
        }
    }
    m_attempts++;
}

void MemoryLearner::push(Input input, uint8_t modes) {
    m_current.push_back(input);
    m_currentModes.push_back(modes);
    m_hash = mix(m_hash, input);
}

void MemoryLearner::startExploring(int tick, int modeP1, int modeP2, bool twoPlayers, bool canGuide, std::mt19937& rng) {
    m_exploring = true;
    // Mostly trust the brain, but the longer this spot resists, the more
    // often try wild ideas instead.
    float trust = std::max(0.25f, 0.85f - 0.04f * (float)m_failsAtFrontier);
    std::uniform_real_distribution<float> chance(0.f, 1.f);
    m_guided = canGuide && chance(rng) < trust;
    m_threshold = 0.35f + 0.3f * chance(rng);
    m_deviateUntil[0] = m_deviateUntil[1] = -1;
    // The first try at a new spot, and the rest of a run that tests a
    // specific fix, show exactly what the brain would do.
    m_pureGuide = canGuide && (m_failsAtFrontier == 0 || m_usingPlan);
    if (m_pureGuide) {
        m_guided = true;
        m_threshold = 0.5f;
    }
    m_state = m_current.empty() ? 0 : m_current.back();
    int modes[2] = {modeP1, modeP2};
    for (int p = 0; p < (twoPlayers ? 2 : 1); p++) {
        bool pressing = (m_state >> p) & 1;
        // Allow switching right away as well as a bit later.
        int span = sampleDuration(modes[p], pressing, rng);
        m_nextSwitch[p] = tick + std::uniform_int_distribution<int>(0, span)(rng);
    }
}

MemoryLearner::Input MemoryLearner::decide(int tick, int modeP1, int modeP2, bool twoPlayers, float const* guide, Input idleMask, std::mt19937& rng) {
    if (tick < 0) tick = 0;
    m_twoPlayers = twoPlayers;
    uint8_t modes = (uint8_t)((modeP1 & 0xF) | ((modeP2 & 0xF) << 4));
    // Ticks normally arrive one by one; fill any gap with the held state so
    // that index == tick holds for the recording.
    while ((int)m_current.size() < tick) {
        Input filler = m_current.empty() ? 0 : m_current.back();
        int at = (int)m_current.size();
        if (at >= (int)m_best.size() || filler != m_best[at]) m_offBestPath = true;
        this->push(filler, modes);
    }
    if ((int)m_current.size() > tick) {
        // Same tick seen again (should not happen) - repeat the decision.
        return m_current[tick];
    }

    auto const& replay = m_usingPlan ? m_plan : m_best;
    Input input;
    bool replaying = tick < m_branch && tick < (int)replay.size();
    if (replaying) {
        input = replay[tick];
    }
    else {
        if (!m_exploring) this->startExploring(tick, modeP1, modeP2, twoPlayers, guide != nullptr, rng);
        int modeOf[2] = {modeP1, modeP2};
        for (int p = 0; p < (twoPlayers ? 2 : 1); p++) {
            if (m_guided && guide) {
                bool want = guide[p] > m_threshold;
                if (tick < m_deviateUntil[p]) {
                    want = !want;
                }
                else if (!m_pureGuide && std::uniform_real_distribution<float>(0.f, 1.f)(rng) < kDeviationPerTick) {
                    m_deviateUntil[p] = tick + sampleDuration(modeOf[p], !want, rng);
                    want = !want;
                }
                m_state = want ? (m_state | (1 << p)) : (m_state & ~(1 << p));
            }
            else if (tick >= m_nextSwitch[p]) {
                m_state ^= (1 << p);
                bool pressing = (m_state >> p) & 1;
                m_nextSwitch[p] = tick + sampleDuration(modeOf[p], pressing, rng);
            }
        }
        input = m_state;
    }

    input &= (Input)~idleMask;
    if (m_exploring) m_state &= (Input)~idleMask;

    // Never replay an input sequence that is already known to be fatal.
    if (m_learning && m_fatal.count(mix(m_hash, input))) {
        Input options = twoPlayers ? 3 : 1;
        for (Input flip = 1; flip <= options; flip++) {
            if (flip & idleMask) continue;
            Input alt = input ^ flip;
            if (!m_fatal.count(mix(m_hash, alt))) {
                input = alt;
                if (m_exploring) m_state = alt;
                break;
            }
        }
    }

    if (tick >= (int)m_best.size() || input != m_best[tick]) m_offBestPath = true;
    this->push(input, modes);
    return input;
}

bool MemoryLearner::onDeath(int tick, float percent) {
    if (!m_learning) return false;

    m_fatal.insert(m_hash);

    if (tick > m_bestTick) {
        bool sameSpot = tick - m_bestTick < kSameSpotTicks;
        // Remember what helped: getting past the spot counts most, but even
        // a little progress shows which way to change things.
        if (m_usingPlan) s_fixWins[statsKey(m_activeFix.situation, m_activeFix.key)] += sameSpot ? 1 : 3;
        m_best = m_current;
        m_bestModes = m_currentModes;
        m_bestTick = tick;
        m_bestPercent = std::max(m_bestPercent, percent);
        m_backoff = kBaseBackoff;
        this->planFixes(tick);
        if (sameSpot) {
            m_deathsAtSpot++;
            // Only a little further: the idea points the right way but was
            // too small. Push the same change harder first.
            if (m_usingPlan) {
                std::vector<Fix> stronger;
                if (m_activeFix.kind == Fix::Toggle) {
                    // A new press that helped a bit: move it around a little.
                    for (int d : {6, -6, 12, -12}) {
                        auto moved = m_activeFix;
                        moved.tick -= d;
                        moved.key = (int16_t)(m_activeFix.key + d); // key holds the distance
                        stronger.push_back(moved);
                    }
                }
                else {
                    for (int percent : {200, 150, 300}) {
                        auto bigger = m_activeFix;
                        bigger.amount = m_activeFix.amount * percent / 100;
                        // The key holds the amount, so the statistics learn the size too.
                        bigger.key = (int16_t)(m_activeFix.key + bigger.amount - m_activeFix.amount);
                        stronger.push_back(bigger);
                    }
                }
                m_fixes.insert(m_fixes.begin(), stronger.begin(), stronger.end());
            }
        }
        else {
            m_deathsAtSpot = 1;
            m_failsAtFrontier = 0;
        }
        return true;
    }

    m_deathsAtSpot++;
    m_failsAtFrontier++;
    if (m_nextFix >= m_fixes.size() && m_failsAtFrontier % kFailsBeforeWidening == 0) {
        // Stuck even after every planned fix: the mistake is further back.
        m_backoff = std::min(std::max(m_bestTick, kBaseBackoff), (int)(m_backoff * 1.6f) + 12);
    }
    return false;
}

void MemoryLearner::adoptCurrentAsBest(int tick) {
    if (!m_learning || m_completed || tick <= 0) return;
    m_best = m_current;
    m_bestModes = m_currentModes;
    m_bestTick = tick;
    m_backoff = kBaseBackoff;
    m_failsAtFrontier = 0;
    m_deathsAtSpot = 1;
    this->planFixes(tick);
}

void MemoryLearner::onComplete(int tick) {
    if (!m_learning || m_completed) return;
    if (m_usingPlan) s_fixWins[statsKey(m_activeFix.situation, m_activeFix.key)] += 3;
    m_best = m_current;
    m_bestModes = m_currentModes;
    m_bestTick = tick;
    m_bestPercent = 100.f;
    m_completed = true;
    m_fixes.clear();
}
