#include "Bot.hpp"
#include "BotPopup.hpp"

#include <Geode/Geode.hpp>
#include <Geode/modify/GJBaseGameLayer.hpp>
#include <Geode/modify/PauseLayer.hpp>
#include <Geode/modify/PlayLayer.hpp>

using namespace geode::prelude;
using namespace aibot;

class $modify(AIBotGameLayer, GJBaseGameLayer) {
    // Runs once per physics tick (240 per second) before inputs are applied,
    // which is where the bot decides whether to hold.
    void processCommands(float dt, bool isHalfTick, bool isLastTick) {
        auto playLayer = PlayLayer::get();
        if (playLayer && static_cast<GJBaseGameLayer*>(playLayer) == this) {
            Bot::get().onTick(playLayer);
        }
        GJBaseGameLayer::processCommands(dt, isHalfTick, isLastTick);
    }

    // While the bot plays, the player's own clicks are ignored.
    void handleButton(bool down, int button, bool isPlayer1) {
        auto& bot = Bot::get();
        auto playLayer = PlayLayer::get();
        if (button == 1 && !bot.isSendingInput() && playLayer &&
            static_cast<GJBaseGameLayer*>(playLayer) == this && bot.isPlaying(playLayer)) {
            return;
        }
        GJBaseGameLayer::handleButton(down, button, isPlayer1);
    }
};

class $modify(AIBotPlayLayer, PlayLayer) {
    bool init(GJGameLevel* level, bool useReplay, bool dontCreateObjects) {
        Bot::get().detach();
        if (!PlayLayer::init(level, useReplay, dontCreateObjects)) return false;
        Bot::get().onLevelEnter(this);
        return true;
    }

    void resetLevel() {
        PlayLayer::resetLevel();
        Bot::get().onAttemptStart(this);
    }

    void destroyPlayer(PlayerObject* player, GameObject* object) {
        // GD "kills" the player with an invisible spike at the start of every
        // attempt as an anti-cheat check; that is not a real death.
        if (object == m_anticheatSpike) {
            PlayLayer::destroyPlayer(player, object);
            return;
        }
        auto& bot = Bot::get();
        // Bot runs are never saved as the player's own progress.
        if (bot.usedThisLevel()) m_isTestMode = true;
        PlayLayer::destroyPlayer(player, object);
        if (player && player->m_isDead) {
            bot.onDeath(this);
        }
    }

    void levelComplete() {
        auto& bot = Bot::get();
        if (bot.usedThisLevel()) m_isTestMode = true;
        bot.onComplete(this);
        PlayLayer::levelComplete();
    }

    void onQuit() {
        Bot::get().onLevelExit(this);
        PlayLayer::onQuit();
    }
};

class $modify(AIBotPauseLayer, PauseLayer) {
    void customSetup() {
        PauseLayer::customSetup();

        auto label = CCLabelBMFont::create("AI", "bigFont.fnt");
        label->setScale(0.6f);
        auto sprite = CircleButtonSprite::create(label, CircleBaseColor::Cyan, CircleBaseSize::Small);
        auto button = CCMenuItemExt::createSpriteExtra(sprite, [](auto) {
            BotPopup::create()->show();
        });
        button->setID("ai-bot-button"_spr);

        auto menu = CCMenu::create();
        menu->setID("ai-bot-menu"_spr);
        auto winSize = CCDirector::get()->getWinSize();
        menu->setPosition({30.f, winSize.height - 30.f});
        menu->addChild(button);
        this->addChild(menu, 10);
    }
};
