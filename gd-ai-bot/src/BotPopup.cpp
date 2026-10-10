#include "BotPopup.hpp"
#include "Bot.hpp"

#include <Geode/Geode.hpp>
#include <Geode/ui/GeodeUI.hpp>

#include <algorithm>
#include <array>
#include <cmath>

using namespace geode::prelude;
using namespace aibot;

namespace {
    constexpr std::array<float, 17> kSpeeds = {
        0.25f, 0.5f, 1.f, 1.5f, 2.f, 3.f, 4.f, 6.f, 8.f, 10.f, 15.f, 20.f, 50.f, 100.f, 200.f, 500.f, 1000.f
    };

    void settingsChanged() {
        Bot::get().reloadConfig();
        Bot::get().applySpeed();
    }

    CCLabelBMFont* rowLabel(char const* text) {
        auto label = CCLabelBMFont::create(text, "bigFont.fnt");
        label->setScale(0.45f);
        label->setAnchorPoint({0.f, 0.5f});
        return label;
    }
}

BotPopup* BotPopup::create() {
    auto ret = new BotPopup();
    if (ret->init()) {
        ret->autorelease();
        return ret;
    }
    delete ret;
    return nullptr;
}

bool BotPopup::init() {
    if (!Popup::init(380.f, 270.f)) return false;
    this->setTitle("AI Bot");

    this->addToggle("Enabled", "enabled", {-170.f, 82.f});
    this->addToggle("Learning", "learning", {20.f, 82.f});

    m_mainLayer->addChildAtPosition(rowLabel("Mode:"), Anchor::Center, {-170.f, 50.f});
    m_memorySprite = ButtonSprite::create("Memory", "bigFont.fnt", "GJ_button_01.png", 0.7f);
    m_humanSprite = ButtonSprite::create("Human", "bigFont.fnt", "GJ_button_01.png", 0.7f);
    m_macroSprite = ButtonSprite::create("Macro", "bigFont.fnt", "GJ_button_01.png", 0.7f);
    for (auto sprite : {m_memorySprite, m_humanSprite, m_macroSprite}) sprite->setScale(0.62f);
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(m_memorySprite, [this](auto) { this->setMode("Memory"); }),
        Anchor::Center, {-50.f, 50.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(m_humanSprite, [this](auto) { this->setMode("Human"); }),
        Anchor::Center, {40.f, 50.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(m_macroSprite, [this](auto) { this->setMode("Macro"); }),
        Anchor::Center, {125.f, 50.f}
    );

    m_mainLayer->addChildAtPosition(rowLabel("Speed:"), Anchor::Center, {-170.f, 18.f});
    auto slower = ButtonSprite::create("-", "bigFont.fnt", "GJ_button_04.png", 0.8f);
    auto faster = ButtonSprite::create("+", "bigFont.fnt", "GJ_button_04.png", 0.8f);
    slower->setScale(0.7f);
    faster->setScale(0.7f);
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(slower, [this](auto) { this->changeSpeed(-1); }),
        Anchor::Center, {-20.f, 18.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(faster, [this](auto) { this->changeSpeed(1); }),
        Anchor::Center, {90.f, 18.f}
    );
    m_speedLabel = CCLabelBMFont::create("", "bigFont.fnt");
    m_speedLabel->setScale(0.5f);
    m_mainLayer->addChildAtPosition(m_speedLabel, Anchor::Center, {35.f, 18.f});

    auto hint = CCLabelBMFont::create("Changes apply from the next attempt", "chatFont.fnt");
    hint->setScale(0.5f);
    hint->setColor({180, 180, 180});
    m_mainLayer->addChildAtPosition(hint, Anchor::Center, {0.f, -2.f});

    m_status = CCLabelBMFont::create("", "chatFont.fnt");
    m_status->setAlignment(kCCTextAlignmentCenter);
    m_status->setScale(0.5f);
    m_mainLayer->addChildAtPosition(m_status, Anchor::Center, {0.f, -50.f});

    auto resetLevel = ButtonSprite::create("Reset level", "goldFont.fnt", "GJ_button_05.png", 0.7f);
    auto resetBrain = ButtonSprite::create("Reset brain", "goldFont.fnt", "GJ_button_05.png", 0.7f);
    auto folder = ButtonSprite::create("Macros", "goldFont.fnt", "GJ_button_02.png", 0.7f);
    auto more = ButtonSprite::create("Settings", "goldFont.fnt", "GJ_button_01.png", 0.7f);
    for (auto sprite : {resetLevel, resetBrain, folder, more}) sprite->setScale(0.58f);

    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(resetLevel, [this](auto) {
            createQuickPopup(
                "Reset level memory",
                "Forget the bot's memory of <cy>this level</c>? Its brain and macros are kept.",
                "Cancel", "Reset",
                [this](auto, bool confirmed) {
                    if (!confirmed) return;
                    Bot::get().resetLevelMemory();
                    this->refresh();
                }
            );
        }),
        Anchor::Center, {-132.f, -108.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(resetBrain, [this](auto) {
            createQuickPopup(
                "Reset brain",
                "Erase everything the bot has learned on <cy>all levels</c> (its brain and experience)? Macros are kept.",
                "Cancel", "Reset",
                [this](auto, bool confirmed) {
                    if (!confirmed) return;
                    Bot::get().resetBrain();
                    this->refresh();
                }
            );
        }),
        Anchor::Center, {-45.f, -108.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(folder, [](auto) {
            Bot::get().openFolder();
        }),
        Anchor::Center, {38.f, -108.f}
    );
    m_buttonMenu->addChildAtPosition(
        CCMenuItemExt::createSpriteExtra(more, [](auto) {
            openSettingsPopup(Mod::get());
        }),
        Anchor::Center, {125.f, -108.f}
    );

    this->refresh();
    return true;
}

void BotPopup::addToggle(char const* text, char const* setting, CCPoint offset) {
    std::string key = setting;
    auto toggle = CCMenuItemExt::createTogglerWithStandardSprites(0.7f, [this, key](CCMenuItemToggler* toggler) {
        // The callback runs before the toggler flips its own state.
        Mod::get()->setSettingValue<bool>(key, !toggler->isToggled());
        settingsChanged();
        this->refresh();
    });
    toggle->toggle(Mod::get()->getSettingValue<bool>(key));
    m_buttonMenu->addChildAtPosition(toggle, Anchor::Center, offset);
    m_mainLayer->addChildAtPosition(rowLabel(text), Anchor::Center, offset + CCPoint{18.f, 0.f});
}

void BotPopup::setMode(char const* mode) {
    Mod::get()->setSettingValue<std::string>("mode", mode);
    settingsChanged();
    this->refresh();
}

void BotPopup::changeSpeed(float direction) {
    float speed = (float)Mod::get()->getSettingValue<double>("speed");
    // Snap to the nearest preset, then step.
    int index = 0;
    for (int i = 0; i < (int)kSpeeds.size(); i++) {
        if (std::abs(kSpeeds[i] - speed) < std::abs(kSpeeds[index] - speed)) index = i;
    }
    index = std::clamp(index + (direction > 0 ? 1 : -1), 0, (int)kSpeeds.size() - 1);
    Mod::get()->setSettingValue<double>("speed", kSpeeds[index]);
    settingsChanged();
    this->refresh();
}

void BotPopup::refresh() {
    auto const& config = Bot::get().config();
    auto pick = [&](LearnMode mode) {
        return config.mode == mode ? "GJ_button_01.png" : "GJ_button_04.png";
    };
    m_memorySprite->updateBGImage(pick(LearnMode::Memory));
    m_humanSprite->updateBGImage(pick(LearnMode::Human));
    m_macroSprite->updateBGImage(pick(LearnMode::Macro));
    m_speedLabel->setString(fmt::format("x{:g}", config.speed).c_str());
    m_status->setString(Bot::get().statusText().c_str());
}

void BotPopup::onClose(CCObject* sender) {
    settingsChanged();
    Popup::onClose(sender);
}
