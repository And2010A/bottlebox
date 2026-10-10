#include "Brain.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>

using namespace aibot;

namespace {
    constexpr char kSkillMagic[8] = {'G', 'D', 'A', 'I', 'S', 'K', 'L', '1'};
    constexpr char kDataMagic[8] = {'G', 'D', 'A', 'I', 'E', 'X', 'P', '1'};
    constexpr size_t kMaxExperience = 120'000;
    constexpr int kBatchSize = 32;
    constexpr float kLearningRate = 0.003f;

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

    // The starting "instinct" for each mode, so a brand new brain does not
    // begin from pure noise: jump modes jump when something dangerous is
    // right ahead, flying modes go up when danger is below and while falling.
    void seedInstinct(float* net, int mode) {
        float* hidden0 = net + kW1;
        for (int i = 0; i < kInputs; i++) hidden0[i] = 0.f;
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

    template <class T>
    void write(std::ofstream& out, T const& value) {
        out.write(reinterpret_cast<char const*>(&value), sizeof(T));
    }

    template <class T>
    bool read(std::ifstream& in, T& value) {
        return static_cast<bool>(in.read(reinterpret_cast<char*>(&value), sizeof(T)));
    }
}

Sample aibot::makeSample(float const* inputs, int mode, bool hold) {
    Sample sample{};
    for (int i = 0; i < kGridInputs; i++) {
        if (inputs[i] > 0.5f) sample.grid[i / 8] |= (uint8_t)(1 << (i % 8));
    }
    std::copy_n(inputs + kGridInputs, kExtraInputs, sample.extra);
    sample.mode = (uint8_t)std::clamp(mode, 0, ModeCount - 1);
    sample.hold = hold ? 1 : 0;
    return sample;
}

void aibot::unpackSample(Sample const& sample, float* inputs) {
    for (int i = 0; i < kGridInputs; i++) {
        inputs[i] = (sample.grid[i / 8] >> (i % 8)) & 1 ? 1.f : 0.f;
    }
    std::copy_n(sample.extra, kExtraInputs, inputs + kGridInputs);
}

void Skill::reset(std::mt19937& rng) {
    std::normal_distribution<float> noise(0.f, 0.08f);
    m_weights.assign(kBrainSize, 0.f);
    for (auto& w : m_weights) w = noise(rng);
    for (int mode = 0; mode < ModeCount; mode++) {
        seedInstinct(m_weights.data() + mode * kNetSize, mode);
    }
    m_adamM.assign(kBrainSize, 0.f);
    m_adamV.assign(kBrainSize, 0.f);
    m_grad.assign(kBrainSize, 0.f);
    m_adamT = 0;
    m_data.clear();
    std::fill(std::begin(m_holdCount), std::end(m_holdCount), 0);
    std::fill(std::begin(m_totalCount), std::end(m_totalCount), 0);
    m_beatenLevels.clear();
    m_movesLearned = 0;
    m_accuracy = 0.f;
}

float Skill::predict(int mode, float const* inputs) const {
    if (m_weights.size() != (size_t)kBrainSize) return 0.f;
    mode = std::clamp(mode, 0, ModeCount - 1);
    float const* net = m_weights.data() + mode * kNetSize;

    float out = net[kB2];
    for (int h = 0; h < kHidden; h++) {
        float const* row = net + kW1 + h * kInputs;
        float sum = net[kB1 + h];
        for (int i = 0; i < kInputs; i++) {
            if (inputs[i] != 0.f) sum += row[i] * inputs[i];
        }
        out += net[kW2 + h] * std::tanh(sum);
    }
    return sigmoid(out);
}

void Skill::addExperience(std::vector<Sample> const& samples, std::mt19937& rng) {
    for (auto const& sample : samples) {
        m_holdCount[sample.mode] += sample.hold;
        m_totalCount[sample.mode]++;
        m_movesLearned++;
        if (m_data.size() < kMaxExperience) {
            m_data.push_back(sample);
        }
        else {
            // Full: replace a random old memory, so old skills fade slowly
            // instead of being cut off.
            m_data[std::uniform_int_distribution<size_t>(0, m_data.size() - 1)(rng)] = sample;
        }
    }
}

void Skill::train(int steps, std::mt19937& rng) {
    if (m_data.empty() || m_weights.empty()) return;
    if (m_grad.size() != (size_t)kBrainSize) {
        m_adamM.assign(kBrainSize, 0.f);
        m_adamV.assign(kBrainSize, 0.f);
        m_grad.assign(kBrainSize, 0.f);
    }
    std::uniform_int_distribution<size_t> pick(0, m_data.size() - 1);
    std::vector<Sample const*> batch(kBatchSize);
    for (int s = 0; s < steps; s++) {
        for (auto& sample : batch) sample = &m_data[pick(rng)];
        this->step(batch);
    }
}

void Skill::step(std::vector<Sample const*> const& batch) {
    bool touched[ModeCount] = {};
    float inputs[kInputs];
    float hidden[kHidden];
    int correct = 0;

    for (auto sample : batch) {
        int mode = sample->mode;
        touched[mode] = true;
        float* net = m_weights.data() + mode * kNetSize;
        float* grad = m_grad.data() + mode * kNetSize;
        unpackSample(*sample, inputs);

        float out = net[kB2];
        for (int h = 0; h < kHidden; h++) {
            float const* row = net + kW1 + h * kInputs;
            float sum = net[kB1 + h];
            for (int i = 0; i < kInputs; i++) {
                if (inputs[i] != 0.f) sum += row[i] * inputs[i];
            }
            hidden[h] = std::tanh(sum);
            out += net[kW2 + h] * hidden[h];
        }
        float p = sigmoid(out);
        float y = sample->hold ? 1.f : 0.f;
        correct += (p > 0.5f) == (y > 0.5f);

        // Holds are rarer than releases in most modes: weigh them up so the
        // brain does not learn "never click".
        float weight = 1.f;
        if (y > 0.5f) {
            auto holds = std::max<uint64_t>(m_holdCount[mode], 1);
            auto releases = m_totalCount[mode] - std::min(m_totalCount[mode], holds);
            weight = std::clamp((float)releases / (float)holds, 1.f, 8.f);
        }

        float dOut = (p - y) * weight;
        grad[kB2] += dOut;
        for (int h = 0; h < kHidden; h++) {
            grad[kW2 + h] += dOut * hidden[h];
            float dHidden = dOut * net[kW2 + h] * (1.f - hidden[h] * hidden[h]);
            grad[kB1 + h] += dHidden;
            float* row = grad + kW1 + h * kInputs;
            for (int i = 0; i < kInputs; i++) {
                if (inputs[i] != 0.f) row[i] += dHidden * inputs[i];
            }
        }
    }

    m_accuracy = m_accuracy * 0.995f + 0.005f * ((float)correct / (float)batch.size());

    // Adam update for the networks used in this batch.
    m_adamT++;
    float scale = 1.f / (float)batch.size();
    float corr1 = 1.f - std::pow(0.9f, (float)m_adamT);
    float corr2 = 1.f - std::pow(0.999f, (float)m_adamT);
    for (int mode = 0; mode < ModeCount; mode++) {
        if (!touched[mode]) continue;
        size_t begin = (size_t)mode * kNetSize, end = begin + kNetSize;
        for (size_t i = begin; i < end; i++) {
            float g = m_grad[i] * scale;
            m_grad[i] = 0.f;
            m_adamM[i] = 0.9f * m_adamM[i] + 0.1f * g;
            m_adamV[i] = 0.999f * m_adamV[i] + 0.001f * g * g;
            float update = kLearningRate * (m_adamM[i] / corr1) / (std::sqrt(m_adamV[i] / corr2) + 1e-6f);
            m_weights[i] = std::clamp(m_weights[i] - update, -12.f, 12.f);
        }
    }
}

void Skill::adoptTraining(Skill const& trained) {
    if (trained.m_weights.size() != (size_t)kBrainSize) return;
    m_weights = trained.m_weights;
    m_adamM = trained.m_adamM;
    m_adamV = trained.m_adamV;
    m_grad.assign(kBrainSize, 0.f);
    m_adamT = trained.m_adamT;
    m_accuracy = trained.m_accuracy;
}

void Skill::markLevelBeaten(std::string const& key) {
    if (!this->hasBeaten(key)) m_beatenLevels.push_back(key);
}

bool Skill::hasBeaten(std::string const& key) const {
    return std::find(m_beatenLevels.begin(), m_beatenLevels.end(), key) != m_beatenLevels.end();
}

int Skill::brainLevel() const {
    return 1 + (int)m_beatenLevels.size() * 2 + (int)std::log2(1.0 + (double)m_movesLearned / 500.0);
}

bool Skill::load(std::filesystem::path const& dir) {
    std::ifstream in(dir / "skill.bin", std::ios::binary);
    if (!in) return false;

    char magic[8];
    if (!in.read(magic, sizeof(magic)) || std::memcmp(magic, kSkillMagic, sizeof(magic)) != 0) return false;

    int32_t size;
    if (!read(in, size) || size != kBrainSize) return false;
    std::vector<float> weights(kBrainSize);
    if (!in.read(reinterpret_cast<char*>(weights.data()), kBrainSize * sizeof(float))) return false;

    uint64_t moves;
    float accuracy;
    uint32_t beatenCount;
    if (!read(in, moves) || !read(in, accuracy) || !read(in, beatenCount) || beatenCount > 100'000) return false;
    std::vector<std::string> beaten;
    for (uint32_t i = 0; i < beatenCount; i++) {
        uint32_t length;
        if (!read(in, length) || length > 256) return false;
        std::string key(length, '\0');
        if (!in.read(key.data(), length)) return false;
        beaten.push_back(std::move(key));
    }

    m_weights = std::move(weights);
    m_adamM.assign(kBrainSize, 0.f);
    m_adamV.assign(kBrainSize, 0.f);
    m_grad.assign(kBrainSize, 0.f);
    m_adamT = 0;
    m_movesLearned = moves;
    m_accuracy = accuracy;
    m_beatenLevels = std::move(beaten);

    // The experience is optional: without it the brain still plays.
    m_data.clear();
    std::fill(std::begin(m_holdCount), std::end(m_holdCount), 0);
    std::fill(std::begin(m_totalCount), std::end(m_totalCount), 0);
    std::ifstream data(dir / "experience.bin", std::ios::binary);
    uint32_t sampleSize, count;
    if (data && data.read(magic, sizeof(magic)) && std::memcmp(magic, kDataMagic, sizeof(magic)) == 0 &&
        read(data, sampleSize) && sampleSize == sizeof(Sample) && read(data, count) && count <= kMaxExperience) {
        std::vector<Sample> samples(count);
        if (data.read(reinterpret_cast<char*>(samples.data()), (std::streamsize)count * sizeof(Sample))) {
            m_data = std::move(samples);
            for (auto const& sample : m_data) {
                if (sample.mode >= ModeCount) continue;
                m_holdCount[sample.mode] += sample.hold;
                m_totalCount[sample.mode]++;
            }
        }
    }
    return true;
}

bool Skill::save(std::filesystem::path const& dir) const {
    if (m_weights.empty()) return false;
    std::error_code ec;
    std::filesystem::create_directories(dir, ec);

    std::ofstream out(dir / "skill.bin", std::ios::binary | std::ios::trunc);
    if (!out) return false;
    out.write(kSkillMagic, sizeof(kSkillMagic));
    write(out, (int32_t)kBrainSize);
    out.write(reinterpret_cast<char const*>(m_weights.data()), kBrainSize * sizeof(float));
    write(out, m_movesLearned);
    write(out, m_accuracy);
    write(out, (uint32_t)m_beatenLevels.size());
    for (auto const& key : m_beatenLevels) {
        write(out, (uint32_t)key.size());
        out.write(key.data(), key.size());
    }
    if (!out) return false;

    std::ofstream data(dir / "experience.bin", std::ios::binary | std::ios::trunc);
    if (!data) return false;
    data.write(kDataMagic, sizeof(kDataMagic));
    write(data, (uint32_t)sizeof(Sample));
    write(data, (uint32_t)m_data.size());
    data.write(reinterpret_cast<char const*>(m_data.data()), (std::streamsize)m_data.size() * sizeof(Sample));
    return static_cast<bool>(data);
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
