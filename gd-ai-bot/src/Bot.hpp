#pragma once

#include "Brain.hpp"
#include "Memory.hpp"
#include "Sensors.hpp"

#include <filesystem>
#include <future>
#include <random>
#include <string>
#include <vector>

class PlayLayer;

namespace cocos2d {
    class CCLabelBMFont;
}

namespace aibot {

enum class LearnMode { Memory, Human, Macro };

struct Config {
    bool enabled = false;
    LearnMode mode = LearnMode::Memory;
    bool learning = true;
    float speed = 1.f;
    int reactionMs = 120;
    int jitterMs = 12;
    float lapsePercent = 0.5f;
    bool showHud = true;
};

class Bot {
public:
    static Bot& get();

    Config const& config() const { return m_config; }
    void reloadConfig();

    // Game events, called from the hooks.
    // Drops every pointer into the current level (saving progress first).
    void detach();
    void onLevelEnter(PlayLayer* layer);
    void onLevelExit(PlayLayer* layer);
    void onAttemptStart(PlayLayer* layer);
    void onTick(PlayLayer* layer);
    void onDeath(PlayLayer* layer);
    void onComplete(PlayLayer* layer);

    // True while the bot plays this attempt (user clicks are ignored).
    bool isPlaying(PlayLayer* layer) const;
    // True if the bot has played at any point since entering the level, so
    // nothing from this session may be saved as the player's own progress.
    bool usedThisLevel() const { return m_usedThisLevel; }
    bool isSendingInput() const { return m_sendingInput; }

    void resetLevelMemory();
    void resetBrain();
    void applySpeed();
    void openFolder();
    std::string statusText() const;

private:
    Bot();

    bool canControl(PlayLayer* layer) const;
    void press(PlayLayer* layer, int player, bool down);
    uint8_t decideHuman(PlayLayer* layer, int tick, bool dual, bool twoPlayers);
    void record(int tick, int player, float const* inputs, int mode, bool hold);

    // Learning from this attempt's moves (ticks [from, to)).
    // Returns how many moments were added to the brain's experience.
    int learnFromRun(int from, int to, int every);
    void scheduleTraining(int steps);
    void pollTraining();
    void ensureBrain();
    void saveBrain();
    void saveMemory();

    void onFirstWin(PlayLayer* layer);
    void saveMacro(PlayLayer* layer);
    void loadMacro();
    void logProgress(char const* event, float percent);
    void updateHud(PlayLayer* layer);
    std::filesystem::path memoryPath() const;

    Config m_config;
    std::mt19937 m_rng;

    MemoryLearner m_memory;
    Skill m_skill;
    bool m_brainLoaded = false;
    std::future<Skill> m_training;
    int m_pendingTraining = 0;
    Sensors m_sensors;
    Hands m_hands;

    // This attempt, tick by tick.
    std::vector<Sample> m_runSamples[2];
    std::vector<uint8_t> m_runInputs;

    // Per level, for this visit.
    int m_learnedUpTo = 0;
    float m_humanBest = 0.f;
    int m_humanAttempts = 0;
    int m_stuckAttempts = 0;
    int m_levelAttempts = 0;
    bool m_beatenThisVisit = false;
    float m_threshold = 0.5f;
    float m_deviationRate = 0.f;
    int m_deviateUntil[2] = {-1, -1};
    float m_lastX[2] = {0.f, 0.f};
    float m_dx[2] = {0.f, 0.f};

    std::vector<uint8_t> m_macro;
    std::string m_macroKey;
    std::string m_macroFile;

    PlayLayer* m_layer = nullptr;
    std::string m_levelKey;
    std::string m_levelName;
    cocos2d::CCLabelBMFont* m_hud = nullptr;

    bool m_attemptPrepared = false;
    bool m_attemptEnded = false;
    bool m_usedThisLevel = false;
    bool m_sendingInput = false;
    bool m_pressed[2] = {false, false};
    bool m_forceSync = true;
    bool m_twoPlayers = false;
    int m_lastTick = -1;
    float m_attemptPercent = 0.f;
    std::string m_lastEvent;
};

}
