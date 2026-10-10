#pragma once

#include <Geode/ui/Popup.hpp>

class ButtonSprite;
class CCMenuItemToggler;

namespace aibot {

// The window opened with the "AI" button in the pause menu.
class BotPopup : public geode::Popup {
public:
    static BotPopup* create();

protected:
    bool init();
    void refresh();
    void onClose(cocos2d::CCObject* sender) override;

    void addToggle(char const* text, char const* setting, cocos2d::CCPoint offset);
    void setMode(char const* mode);
    void changeSpeed(float delta);

    ButtonSprite* m_memorySprite = nullptr;
    ButtonSprite* m_humanSprite = nullptr;
    cocos2d::CCLabelBMFont* m_speedLabel = nullptr;
    cocos2d::CCLabelBMFont* m_status = nullptr;
};

}
