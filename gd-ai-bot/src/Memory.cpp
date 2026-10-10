#include "Memory.hpp"
#include "Common.hpp"

#include <algorithm>
#include <cmath>
#include <climits>
#include <cstring>
#include <fstream>

using namespace aibot;

namespace {
    constexpr char kMagic[8] = {'G', 'D', 'A', 'I', 'M', 'E', 'M', '1'};
    constexpr uint64_t kHashSeed = 0x9E3779B97F4A7C15ull;
    // How far back (in ticks) from the furthest death a new try starts.
    constexpr int kBaseBackoff = 48;
    // After this many failures at the same frontier, look further back.
    constexpr int kFailsBeforeWidening = 8;

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

    int sampleDuration(int mode, bool pressing, std::mt19937& rng) {
        auto range = holdRange(mode);
        int lo = pressing ? range.pressMin : range.releaseMin;
        int hi = pressing ? range.pressMax : range.releaseMax;
        // Log-uniform, so short taps and long holds are both common.
        std::uniform_real_distribution<float> dist(std::log((float)lo), std::log((float)hi + 1.f));
        return std::max(1, (int)std::exp(dist(rng)));
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

void MemoryLearner::clear() {
    *this = MemoryLearner();
}

bool MemoryLearner::load(std::filesystem::path const& path) {
    this->clear();
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;

    char magic[8];
    if (!in.read(magic, sizeof(magic)) || std::memcmp(magic, kMagic, sizeof(magic)) != 0) return false;

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

    m_best = std::move(best);
    m_bestTick = bestTick;
    m_bestPercent = bestPercent;
    m_completed = completed != 0;
    m_attempts = attempts;
    return true;
}

bool MemoryLearner::save(std::filesystem::path const& path) const {
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return false;

    out.write(kMagic, sizeof(kMagic));
    write(out, (int32_t)m_bestTick);
    write(out, m_bestPercent);
    write(out, (uint8_t)m_completed);
    write(out, (int32_t)m_attempts);
    write(out, (uint32_t)m_best.size());
    out.write(reinterpret_cast<char const*>(m_best.data()), m_best.size());
    return static_cast<bool>(out);
}

void MemoryLearner::beginAttempt(bool learning, std::mt19937& rng) {
    m_learning = learning;
    m_current.clear();
    m_hash = kHashSeed;
    m_exploring = false;
    m_state = 0;
    if (m_backoff <= 0) m_backoff = kBaseBackoff;

    if (!learning || m_completed) {
        // Just show what is known.
        m_branch = INT_MAX;
    }
    else if (m_best.empty()) {
        m_branch = 0;
    }
    else {
        int lo = std::max(0, m_bestTick - m_backoff);
        int hi = std::max(lo, m_bestTick - 1);
        m_branch = std::uniform_int_distribution<int>(lo, hi)(rng);
    }
    m_attempts++;
}

void MemoryLearner::push(Input input) {
    m_current.push_back(input);
    m_hash = mix(m_hash, input);
}

void MemoryLearner::startExploring(int tick, int modeP1, int modeP2, bool twoPlayers, std::mt19937& rng) {
    m_exploring = true;
    m_state = m_current.empty() ? 0 : m_current.back();
    int modes[2] = {modeP1, modeP2};
    for (int p = 0; p < (twoPlayers ? 2 : 1); p++) {
        bool pressing = (m_state >> p) & 1;
        // Allow switching right away as well as a bit later.
        int span = sampleDuration(modes[p], pressing, rng);
        m_nextSwitch[p] = tick + std::uniform_int_distribution<int>(0, span)(rng);
    }
}

MemoryLearner::Input MemoryLearner::decide(int tick, int modeP1, int modeP2, bool twoPlayers, std::mt19937& rng) {
    if (tick < 0) tick = 0;
    // Ticks normally arrive one by one; fill any gap with the held state so
    // that index == tick holds for the recording.
    while ((int)m_current.size() < tick) {
        this->push(m_current.empty() ? 0 : m_current.back());
    }
    if ((int)m_current.size() > tick) {
        // Same tick seen again (should not happen) - repeat the decision.
        return m_current[tick];
    }

    Input input;
    bool replaying = tick < m_branch && tick < (int)m_best.size();
    if (replaying) {
        input = m_best[tick];
    }
    else {
        if (!m_exploring) this->startExploring(tick, modeP1, modeP2, twoPlayers, rng);
        int modes[2] = {modeP1, modeP2};
        for (int p = 0; p < (twoPlayers ? 2 : 1); p++) {
            if (tick >= m_nextSwitch[p]) {
                m_state ^= (1 << p);
                bool pressing = (m_state >> p) & 1;
                m_nextSwitch[p] = tick + sampleDuration(modes[p], pressing, rng);
            }
        }
        input = m_state;
    }

    // Never replay an input sequence that is already known to be fatal.
    if (m_learning && m_fatal.count(mix(m_hash, input))) {
        Input options = twoPlayers ? 3 : 1;
        for (Input flip = 1; flip <= options; flip++) {
            Input alt = input ^ flip;
            if (!m_fatal.count(mix(m_hash, alt))) {
                input = alt;
                if (m_exploring) m_state = alt;
                break;
            }
        }
    }

    this->push(input);
    return input;
}

bool MemoryLearner::onDeath(int tick, float percent) {
    if (!m_learning) return false;

    m_fatal.insert(m_hash);

    if (tick > m_bestTick) {
        m_best = m_current;
        m_bestTick = tick;
        m_bestPercent = std::max(m_bestPercent, percent);
        m_failsAtFrontier = 0;
        m_backoff = kBaseBackoff;
        return true;
    }

    m_failsAtFrontier++;
    if (m_failsAtFrontier % kFailsBeforeWidening == 0) {
        // Stuck: the mistake is probably further back.
        m_backoff = std::min(std::max(m_bestTick, kBaseBackoff), (int)(m_backoff * 1.6f) + 12);
    }
    return false;
}

void MemoryLearner::onComplete(int tick) {
    if (!m_learning || m_completed) return;
    m_best = m_current;
    m_bestTick = tick;
    m_bestPercent = 100.f;
    m_completed = true;
}
