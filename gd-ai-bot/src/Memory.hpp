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
//
// New moves are not purely random: most tries follow the shared brain's
// suggestion (what worked on other levels), with occasional deviations, so
// experience from beaten levels makes new levels go much faster.
class MemoryLearner {
public:
    // Which kinds of fixes have worked before, per game mode, shared by all
    // levels: the bot learns how to fix its mistakes, and tries the fixes
    // that usually work first.
    static bool loadFixStats(std::filesystem::path const& path);
    static bool saveFixStats(std::filesystem::path const& path);
    static void resetFixStats();

    // Bit 0 = player 1 holds, bit 1 = player 2 holds (two-player levels).
    using Input = uint8_t;

    void clear();
    bool load(std::filesystem::path const& path);
    bool save(std::filesystem::path const& path) const;

    void beginAttempt(bool learning, std::mt19937& rng);
    // `guide` holds the brain's hold probability for each player, or is null.
    // `idleMask` marks players for whom a click cannot matter right now (a
    // cube in mid-air with no orb near): they never press then, so every
    // remembered press really is a jump and every fix changes something.
    Input decide(int tick, int modeP1, int modeP2, bool twoPlayers, float const* guide, Input idleMask, std::mt19937& rng);
    // Returns true if this attempt went further than any before.
    bool onDeath(int tick, float percent);
    void onComplete(int tick);

    // What the current attempt is testing, for the HUD ("jump earlier"...),
    // or null when it is not testing a specific fix.
    char const* currentIdea() const { return m_usingPlan ? m_idea : nullptr; }
    // Deaths at the current furthest spot so far.
    int deathsAtSpot() const { return m_deathsAtSpot; }

    int bestTick() const { return m_bestTick; }
    float bestPercent() const { return m_bestPercent; }
    bool completed() const { return m_completed; }
    int attempts() const { return m_attempts; }
    int branchTick() const { return m_branch; }
    bool exploring() const { return m_exploring; }
    bool guided() const { return m_guided; }
    // The inputs of the attempt so far, one per tick.
    std::vector<Input> const& currentRun() const { return m_current; }

private:
    // One idea for fixing the latest death, tested on a single attempt.
    struct Fix {
        enum Kind : uint8_t { Shift, Resize, Toggle } kind;
        uint8_t player;
        int tick;   // Shift/Resize: index of the press; Toggle: first tick
        int amount; // Shift/Resize: ticks to move; Toggle: length
        uint8_t situation; // game mode + whether a press came shortly before
        int16_t key;       // what kind of fix this is, for the statistics
    };

    void push(Input input, uint8_t modes);
    void planFixes(int deathTick);
    bool buildPlan(Fix const& fix, std::vector<Input>& plan) const;
    void startExploring(int tick, int modeP1, int modeP2, bool twoPlayers, bool canGuide, std::mt19937& rng);

    std::vector<Input> m_best;
    int m_bestTick = 0;
    float m_bestPercent = 0.f;
    bool m_completed = false;
    int m_attempts = 0;

    // Game mode per tick (player 1 in the low 4 bits, player 2 above).
    std::vector<uint8_t> m_bestModes;
    std::vector<uint8_t> m_currentModes;

    std::vector<Input> m_current;
    uint64_t m_hash = 0;
    std::unordered_set<uint64_t> m_fatal;

    bool m_learning = true;
    int m_branch = 0;
    int m_backoff = 0;
    int m_failsAtFrontier = 0;
    int m_deathsAtSpot = 0;

    std::vector<Fix> m_fixes;
    size_t m_nextFix = 0;
    std::unordered_set<uint64_t> m_triedPlans;
    std::vector<Input> m_plan;
    bool m_usingPlan = false;
    char const* m_idea = nullptr;
    Fix m_activeFix{};
    bool m_twoPlayers = false;

    bool m_exploring = false;
    Input m_state = 0;
    int m_nextSwitch[2] = {0, 0};
    bool m_guided = false;
    bool m_pureGuide = false;
    float m_threshold = 0.5f;
    int m_deviateUntil[2] = {-1, -1};
};

}
