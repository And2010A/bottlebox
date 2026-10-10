#pragma once

#include "Common.hpp"

#include <cstdint>
#include <deque>
#include <filesystem>
#include <random>
#include <string>
#include <vector>

namespace aibot {

// What the bot "sees": a grid of cells around the player, one block (30
// units) each, with separate channels for solids, hazards and orbs/pads.
constexpr int kGridCols = 8;   // from half a block behind to ~7.5 blocks ahead
constexpr int kGridRows = 7;   // three blocks below to three blocks above
constexpr int kGridChannels = 3;
constexpr float kCellSize = 30.f;
constexpr int kGridInputs = kGridCols * kGridRows * kGridChannels;

enum Channel : int { SolidChannel = 0, HazardChannel = 1, OrbChannel = 2 };

// Extra inputs after the grid: vertical speed, on ground, upside down,
// horizontal speed, mini size, dual.
constexpr int kExtraInputs = 6;
constexpr int kInputs = kGridInputs + kExtraInputs;
constexpr int kHidden = 16;
// One small network per game mode.
constexpr int kNetSize = kInputs * kHidden + kHidden + kHidden + 1;
constexpr int kBrainSize = kNetSize * ModeCount;

inline int gridIndex(int channel, int col, int row) {
    return (channel * kGridRows + row) * kGridCols + col;
}

// One remembered moment: what the bot saw and whether it held.
struct Sample {
    uint8_t grid[(kGridInputs + 7) / 8];
    float extra[kExtraInputs];
    uint8_t mode;
    uint8_t hold;
};

Sample makeSample(float const* inputs, int mode, bool hold);
void unpackSample(Sample const& sample, float* inputs);

// The bot's experience, shared by every level. It learns by imitating the
// moves from its own successful runs (everything it survived), so a level
// it has beaten teaches it things it can use on the next one.
class Skill {
public:
    void reset(std::mt19937& rng);
    bool load(std::filesystem::path const& dir);
    bool save(std::filesystem::path const& dir) const;

    bool empty() const { return m_weights.empty(); }
    // Probability (0..1) that holding is right here.
    float predict(int mode, float const* inputs) const;

    void addExperience(std::vector<Sample> const& samples, std::mt19937& rng);
    void train(int steps, std::mt19937& rng);
    // Takes the networks from a copy that was trained in the background,
    // keeping this brain's own (possibly newer) experience.
    void adoptTraining(Skill const& trained);

    // Progress shown to the player.
    void markLevelBeaten(std::string const& key);
    int levelsBeaten() const { return (int)m_beatenLevels.size(); }
    bool hasBeaten(std::string const& key) const;
    uint64_t movesLearned() const { return m_movesLearned; }
    size_t experienceSize() const { return m_data.size(); }
    float accuracy() const { return m_accuracy; }
    // A rough "level" of the brain that grows with what it knows.
    int brainLevel() const;

private:
    void step(std::vector<Sample const*> const& batch);

    std::vector<float> m_weights;
    std::vector<float> m_adamM, m_adamV, m_grad;
    int64_t m_adamT = 0;

    std::vector<Sample> m_data;
    uint64_t m_holdCount[ModeCount] = {};
    uint64_t m_totalCount[ModeCount] = {};

    std::vector<std::string> m_beatenLevels;
    uint64_t m_movesLearned = 0;
    float m_accuracy = 0.f;
};

// Human-like execution of the brain's wishes: presses happen after a
// reaction delay, with timing errors and the occasional missed click.
class Hands {
public:
    void reset();
    void want(int player, bool hold, int tick, int delayTicks, int jitterTicks, float lapseChance, std::mt19937& rng);
    bool apply(int player, int tick);
    bool wanted(int player) const { return m_wanted[player]; }

private:
    struct Pending {
        int tick;
        bool hold;
    };
    std::deque<Pending> m_pending[2];
    bool m_wanted[2] = {false, false};
    bool m_actual[2] = {false, false};
    int m_lastScheduled[2] = {0, 0};
};

}
