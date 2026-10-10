#pragma once

#include "Common.hpp"

#include <deque>
#include <filesystem>
#include <random>
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

// Extra inputs after the grid: vertical speed, on ground, holding,
// horizontal speed, mini size, dual.
constexpr int kExtraInputs = 6;
constexpr int kInputs = kGridInputs + kExtraInputs;
constexpr int kHidden = 12;
// One small network per game mode.
constexpr int kNetSize = kInputs * kHidden + kHidden + kHidden + 1;
constexpr int kGenomeSize = kNetSize * ModeCount;

inline int gridIndex(int channel, int col, int row) {
    return (channel * kGridRows + row) * kGridCols + col;
}

struct Genome {
    std::vector<float> weights;
    float fitness = -1.f;
};

// Probability (0..1) that the network for `mode` wants to hold.
float evaluate(Genome const& genome, int mode, float const* inputs);

// Neuro-evolution: every attempt tries one genome; after the whole
// population has played, the best ones are kept and mutated.
class Population {
public:
    void reset(int size, std::mt19937& rng);
    bool load(std::filesystem::path const& path);
    bool save(std::filesystem::path const& path) const;

    bool empty() const { return m_genomes.empty(); }
    Genome const& current() const { return m_genomes[m_index]; }
    Genome const& champion() const { return m_champion; }
    // Returns true when a new generation was created.
    bool report(float fitness, int nextSize, float mutationRate, std::mt19937& rng);

    int generation() const { return m_generation; }
    int index() const { return m_index; }
    int size() const { return (int)m_genomes.size(); }
    float bestFitness() const { return m_champion.fitness; }

private:
    void evolve(int nextSize, float mutationRate, std::mt19937& rng);

    std::vector<Genome> m_genomes;
    Genome m_champion;
    int m_index = 0;
    int m_generation = 1;
};

// Human-like execution of the network's wishes: presses happen after a
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
