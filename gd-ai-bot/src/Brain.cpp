#include "Brain.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>

using namespace aibot;

namespace {
    constexpr char kMagic[8] = {'G', 'D', 'A', 'I', 'B', 'R', 'N', '1'};

    // Offsets inside one mode's network.
    constexpr int kW1 = 0;
    constexpr int kB1 = kW1 + kInputs * kHidden;
    constexpr int kW2 = kB1 + kHidden;
    constexpr int kB2 = kW2 + kHidden;

    float sigmoid(float x) {
        return 1.f / (1.f + std::exp(-x));
    }

    bool isJumpMode(int mode) {
        return mode == Cube || mode == Ball || mode == Ufo || mode == Robot || mode == Spider;
    }

    // The starting "instinct" for each mode, so the bot does not begin from
    // pure noise: jump modes jump when something dangerous is right ahead,
    // flying modes go up when danger is below and while falling.
    void seedInstinct(float* net, int mode) {
        float* hidden0 = net + kW1;
        if (isJumpMode(mode)) {
            for (int col = 1; col <= 2; col++) {
                for (int row = 2; row <= 4; row++) {
                    hidden0[gridIndex(HazardChannel, col, row)] = 2.f;
                }
            }
            hidden0[gridIndex(SolidChannel, 1, 3)] = 1.5f;
            net[kB1 + 0] = -1.f;
            net[kW2 + 0] = 5.f;
            net[kB2] = -3.f;
        }
        else {
            for (int col = 1; col <= 4; col++) {
                for (int row = 0; row <= 2; row++) {
                    hidden0[gridIndex(HazardChannel, col, row)] = 1.f;
                    hidden0[gridIndex(SolidChannel, col, row)] = 0.5f;
                }
                for (int row = 4; row < kGridRows; row++) {
                    hidden0[gridIndex(HazardChannel, col, row)] = -1.f;
                    hidden0[gridIndex(SolidChannel, col, row)] = -0.5f;
                }
            }
            // Input 0 after the grid is the vertical speed: falling -> hold.
            hidden0[kGridInputs + 0] = -1.5f;
            net[kB1 + 0] = 0.f;
            net[kW2 + 0] = 4.f;
            net[kB2] = 0.f;
        }
    }

    Genome instinctGenome(std::mt19937& rng) {
        std::normal_distribution<float> noise(0.f, 0.1f);
        Genome genome;
        genome.weights.resize(kGenomeSize);
        for (auto& w : genome.weights) w = noise(rng);
        for (int mode = 0; mode < ModeCount; mode++) {
            float* net = genome.weights.data() + mode * kNetSize;
            // Clear the first hidden neuron before giving it its instinct.
            for (int i = 0; i < kInputs; i++) net[kW1 + i] = 0.f;
            seedInstinct(net, mode);
        }
        return genome;
    }

    void mutate(Genome& genome, float rate, float strength, std::mt19937& rng) {
        std::uniform_real_distribution<float> chance(0.f, 1.f);
        std::normal_distribution<float> noise(0.f, strength);
        for (auto& w : genome.weights) {
            if (chance(rng) < rate) {
                w = std::clamp(w + noise(rng), -8.f, 8.f);
            }
        }
        genome.fitness = -1.f;
    }

    template <class T>
    void write(std::ofstream& out, T const& value) {
        out.write(reinterpret_cast<char const*>(&value), sizeof(T));
    }

    template <class T>
    bool read(std::ifstream& in, T& value) {
        return static_cast<bool>(in.read(reinterpret_cast<char*>(&value), sizeof(T)));
    }

    bool readWeights(std::ifstream& in, Genome& genome) {
        genome.weights.resize(kGenomeSize);
        return read(in, genome.fitness) &&
            in.read(reinterpret_cast<char*>(genome.weights.data()), kGenomeSize * sizeof(float));
    }

    void writeWeights(std::ofstream& out, Genome const& genome) {
        write(out, genome.fitness);
        out.write(reinterpret_cast<char const*>(genome.weights.data()), kGenomeSize * sizeof(float));
    }
}

float aibot::evaluate(Genome const& genome, int mode, float const* inputs) {
    if (genome.weights.size() != (size_t)kGenomeSize) return 0.f;
    mode = std::clamp(mode, 0, ModeCount - 1);
    float const* net = genome.weights.data() + mode * kNetSize;

    float out = net[kB2];
    for (int h = 0; h < kHidden; h++) {
        float const* row = net + kW1 + h * kInputs;
        float sum = net[kB1 + h];
        for (int i = 0; i < kInputs; i++) {
            sum += row[i] * inputs[i];
        }
        out += net[kW2 + h] * std::tanh(sum);
    }
    return sigmoid(out);
}

void Population::reset(int size, std::mt19937& rng) {
    size = std::max(size, 2);
    m_genomes.clear();
    m_genomes.push_back(instinctGenome(rng));
    while ((int)m_genomes.size() < size) {
        auto genome = m_genomes.front();
        mutate(genome, 0.2f, 0.5f, rng);
        m_genomes.push_back(std::move(genome));
    }
    m_champion = m_genomes.front();
    m_champion.fitness = -1.f;
    m_index = 0;
    m_generation = 1;
}

bool Population::report(float fitness, int nextSize, float mutationRate, std::mt19937& rng) {
    if (m_genomes.empty()) return false;

    auto& genome = m_genomes[m_index];
    genome.fitness = fitness;
    if (fitness > m_champion.fitness) {
        m_champion = genome;
    }

    m_index++;
    if (m_index < (int)m_genomes.size()) return false;

    this->evolve(nextSize, mutationRate, rng);
    return true;
}

void Population::evolve(int nextSize, float mutationRate, std::mt19937& rng) {
    nextSize = std::max(nextSize, 2);
    std::sort(m_genomes.begin(), m_genomes.end(), [](Genome const& a, Genome const& b) {
        return a.fitness > b.fitness;
    });

    int elites = std::max(2, nextSize / 5);
    int parents = std::max(2, (int)m_genomes.size() / 2);

    std::vector<Genome> next;
    next.reserve(nextSize);

    // The all-time champion always survives, so a lucky run is not lost.
    next.push_back(m_champion);
    for (int i = 0; i < (int)m_genomes.size() && (int)next.size() < elites; i++) {
        next.push_back(m_genomes[i]);
    }

    std::uniform_int_distribution<int> pick(0, parents - 1);
    std::uniform_real_distribution<float> chance(0.f, 1.f);
    auto tournament = [&]() -> Genome const& {
        int a = pick(rng), b = pick(rng), c = pick(rng);
        int best = std::min({a, b, c}); // sorted, so lower index = fitter
        return m_genomes[best];
    };

    while ((int)next.size() < nextSize) {
        auto const& mom = tournament();
        auto const& dad = tournament();
        Genome child;
        child.weights.resize(kGenomeSize);
        // Inherit each mode's network as a whole from one of the parents.
        for (int mode = 0; mode < ModeCount; mode++) {
            auto const& src = chance(rng) < 0.5f ? mom : dad;
            std::copy_n(src.weights.begin() + mode * kNetSize, kNetSize, child.weights.begin() + mode * kNetSize);
        }
        bool bold = chance(rng) < 0.1f;
        mutate(child, bold ? mutationRate * 4.f : mutationRate, bold ? 0.8f : 0.35f, rng);
        next.push_back(std::move(child));
    }

    for (auto& genome : next) genome.fitness = -1.f;
    m_genomes = std::move(next);
    m_index = 0;
    m_generation++;
}

bool Population::load(std::filesystem::path const& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) return false;

    char magic[8];
    if (!in.read(magic, sizeof(magic)) || std::memcmp(magic, kMagic, sizeof(magic)) != 0) return false;

    int32_t genomeSize, generation, index, count;
    if (!read(in, genomeSize) || !read(in, generation) || !read(in, index) || !read(in, count)) return false;
    if (genomeSize != kGenomeSize || count < 1 || count > 256) return false;

    Genome champion;
    if (!readWeights(in, champion)) return false;

    std::vector<Genome> genomes(count);
    for (auto& genome : genomes) {
        if (!readWeights(in, genome)) return false;
    }

    m_champion = std::move(champion);
    m_genomes = std::move(genomes);
    m_generation = generation;
    m_index = std::clamp(index, 0, count - 1);
    return true;
}

bool Population::save(std::filesystem::path const& path) const {
    if (m_genomes.empty()) return false;
    std::error_code ec;
    std::filesystem::create_directories(path.parent_path(), ec);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return false;

    out.write(kMagic, sizeof(kMagic));
    write(out, (int32_t)kGenomeSize);
    write(out, (int32_t)m_generation);
    write(out, (int32_t)m_index);
    write(out, (int32_t)m_genomes.size());
    writeWeights(out, m_champion);
    for (auto const& genome : m_genomes) writeWeights(out, genome);
    return static_cast<bool>(out);
}

void Hands::reset() {
    for (int p = 0; p < 2; p++) {
        m_pending[p].clear();
        m_wanted[p] = false;
        m_actual[p] = false;
        m_lastScheduled[p] = 0;
    }
}

void Hands::want(int player, bool hold, int tick, int delayTicks, int jitterTicks, float lapseChance, std::mt19937& rng) {
    if (m_wanted[player] == hold) return;
    m_wanted[player] = hold;

    if (hold && lapseChance > 0.f && std::uniform_real_distribution<float>(0.f, 1.f)(rng) < lapseChance) {
        // Missed this press entirely.
        return;
    }

    int at = tick + delayTicks;
    if (jitterTicks > 0) {
        at += std::uniform_int_distribution<int>(-jitterTicks, jitterTicks)(rng);
    }
    at = std::max({at, tick, m_lastScheduled[player]});
    m_lastScheduled[player] = at;
    m_pending[player].push_back({at, hold});
}

bool Hands::apply(int player, int tick) {
    auto& queue = m_pending[player];
    while (!queue.empty() && queue.front().tick <= tick) {
        m_actual[player] = queue.front().hold;
        queue.pop_front();
    }
    return m_actual[player];
}
