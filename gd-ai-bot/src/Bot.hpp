#pragma once

#include "Brain.hpp"
#include "Memory.hpp"
#include "Sensors.hpp"

#include <filesystem>
#include <random>
#include <string>

class PlayLayer;

namespace cocos2d {
    class CCLabelBMFont;
}

namespace aibot {

enum class LearnMode { Memory, Human };

struct Config {
    bool enabled = false;
    LearnMode mode = LearnMode::Memory;
    bool learning = true;
    float speed = 1.f;
    int reactionMs = 120;
    int jitterMs = 12;
    float lapsePercent = 0.5f;
    int population = 20;
    float mutationRate = 0.05f;
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
    std::string statusText() const;

private:
    Bot();

    bool canControl(PlayLayer* layer) const;
    void press(PlayLayer* layer, int player, bool down);
    uint8_t decideHuman(PlayLayer* layer, int tick, bool dual, bool twoPlayers);
    void ensureBrain();
    void saveBrain();
    void saveMemory();
    void updateHud(PlayLayer* layer);
    std::filesystem::path memoryPath() const;

    Config m_config;
    std::mt19937 m_rng;

    MemoryLearner m_memory;
    Population m_population;
    bool m_brainLoaded = false;
    Sensors m_sensors;
    Hands m_hands;

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
    int m_lastTick = -1;
    float m_attemptPercent = 0.f;
    float m_humanBestPercent = 0.f;
    int m_humanAttempts = 0;
    std::string m_lastEvent;
};

}
