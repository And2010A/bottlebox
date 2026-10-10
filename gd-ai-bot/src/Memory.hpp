#pragma once

#include <cstdint>
#include <filesystem>
#include <random>
#include <unordered_set>
#include <vector>

namespace aibot {

// "Memory" mode: a deterministic search over input sequences.
//
// GD physics runs on fixed ticks, so replaying the same presses on the same
// ticks reproduces the same run. The learner keeps the furthest run so far,
// replays it up to a point shortly before where it died and tries something
// new from there. Every input prefix that ended in a death is remembered and
// never played again, so the bot never dies the same way twice and never
// dies before the furthest point it has already survived.
class MemoryLearner {
public:
    // Bit 0 = player 1 holds, bit 1 = player 2 holds (two-player levels).
    using Input = uint8_t;

    void clear();
    bool load(std::filesystem::path const& path);
    bool save(std::filesystem::path const& path) const;

    void beginAttempt(bool learning, std::mt19937& rng);
    Input decide(int tick, int modeP1, int modeP2, bool twoPlayers, std::mt19937& rng);
    // Returns true if this attempt went further than any before.
    bool onDeath(int tick, float percent);
    void onComplete(int tick);

    int bestTick() const { return m_bestTick; }
    float bestPercent() const { return m_bestPercent; }
    bool completed() const { return m_completed; }
    int attempts() const { return m_attempts; }
    int branchTick() const { return m_branch; }
    bool exploring() const { return m_exploring; }

private:
    void push(Input input);
    void startExploring(int tick, int modeP1, int modeP2, bool twoPlayers, std::mt19937& rng);

    std::vector<Input> m_best;
    int m_bestTick = 0;
    float m_bestPercent = 0.f;
    bool m_completed = false;
    int m_attempts = 0;

    std::vector<Input> m_current;
    uint64_t m_hash = 0;
    std::unordered_set<uint64_t> m_fatal;

    bool m_learning = true;
    int m_branch = 0;
    int m_backoff = 0;
    int m_failsAtFrontier = 0;

    bool m_exploring = false;
    Input m_state = 0;
    int m_nextSwitch[2] = {0, 0};
};

}
