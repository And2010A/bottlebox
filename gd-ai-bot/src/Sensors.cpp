#include "Sensors.hpp"

#include <Geode/Geode.hpp>

#include <algorithm>
#include <cmath>

using namespace geode::prelude;
using namespace aibot;

namespace {
    int channelOf(GameObjectType type) {
        switch (type) {
            case GameObjectType::Solid:
            case GameObjectType::Slope:
            case GameObjectType::Breakable:
                return SolidChannel;

            case GameObjectType::Hazard:
            case GameObjectType::AnimatedHazard:
                return HazardChannel;

            case GameObjectType::YellowJumpPad:
            case GameObjectType::PinkJumpPad:
            case GameObjectType::RedJumpPad:
            case GameObjectType::GravityPad:
            case GameObjectType::SpiderPad:
            case GameObjectType::YellowJumpRing:
            case GameObjectType::PinkJumpRing:
            case GameObjectType::RedJumpRing:
            case GameObjectType::GravityRing:
            case GameObjectType::GreenRing:
            case GameObjectType::DropRing:
            case GameObjectType::CustomRing:
            case GameObjectType::DashRing:
            case GameObjectType::GravityDashRing:
            case GameObjectType::SpiderOrb:
            case GameObjectType::TeleportOrb:
                return OrbChannel;

            default:
                return -1;
        }
    }

    // Objects can be moved by triggers; look a bit wider than the grid.
    constexpr float kSearchMargin = 150.f;
}

int aibot::modeOf(PlayerObject* player) {
    if (!player) return Cube;
    if (player->m_isShip) return Ship;
    if (player->m_isBall) return Ball;
    if (player->m_isBird) return Ufo;
    if (player->m_isDart) return Wave;
    if (player->m_isRobot) return Robot;
    if (player->m_isSpider) return Spider;
    if (player->m_isSwing) return Swing;
    return Cube;
}

void Sensors::clear() {
    m_entries.clear();
    m_layer = nullptr;
    m_objectCount = 0;
}

void Sensors::prepare(GJBaseGameLayer* layer) {
    if (!layer || !layer->m_objects) {
        this->clear();
        return;
    }
    unsigned int count = layer->m_objects->count();
    if (layer == m_layer && count == m_objectCount) return;

    m_entries.clear();
    m_layer = layer;
    m_objectCount = count;

    for (auto object : CCArrayExt<GameObject*>(layer->m_objects)) {
        if (!object) continue;
        int channel = channelOf(object->m_objectType);
        if (channel < 0) continue;
        m_entries.push_back({(float)object->m_positionX, object, channel});
    }
    std::sort(m_entries.begin(), m_entries.end(), [](Entry const& a, Entry const& b) {
        return a.x < b.x;
    });
}

void Sensors::observe(PlayerObject* player, bool dual, float* out, float lookahead) const {
    std::fill(out, out + kInputs, 0.f);
    if (!player) return;

    float px = player->m_position.x + lookahead;
    float py = player->m_position.y;
    bool flipped = player->m_isUpsideDown;

    // Column 0 starts half a block behind the player; the player is in the
    // middle row.
    float gridLeft = px - kCellSize * 0.5f;
    float gridBottom = py - kCellSize * kGridRows * 0.5f;
    float gridRight = gridLeft + kCellSize * kGridCols;
    float gridTop = gridBottom + kCellSize * kGridRows;

    auto first = std::lower_bound(m_entries.begin(), m_entries.end(), gridLeft - kSearchMargin, [](Entry const& e, float x) {
        return e.x < x;
    });

    for (auto it = first; it != m_entries.end() && it->x <= gridRight + kSearchMargin; ++it) {
        auto object = it->object;
        if (object->m_isGroupDisabled || object->m_isNoTouch) continue;

        auto const& rect = object->getObjectRect();
        float minX = rect.getMinX(), maxX = rect.getMaxX();
        float minY = rect.getMinY(), maxY = rect.getMaxY();
        if (maxX < gridLeft || minX > gridRight || maxY < gridBottom || minY > gridTop) continue;

        int c0 = std::max(0, (int)std::floor((minX - gridLeft) / kCellSize));
        int c1 = std::min(kGridCols - 1, (int)std::floor((maxX - gridLeft) / kCellSize));
        int r0 = std::max(0, (int)std::floor((minY - gridBottom) / kCellSize));
        int r1 = std::min(kGridRows - 1, (int)std::floor((maxY - gridBottom) / kCellSize));

        for (int col = c0; col <= c1; col++) {
            for (int row = r0; row <= r1; row++) {
                // Upside down, "below" means towards the ceiling, so the
                // same knowledge works with either gravity.
                int seenRow = flipped ? kGridRows - 1 - row : row;
                out[gridIndex(it->channel, col, seenRow)] = 1.f;
            }
        }
    }

    float* extra = out + kGridInputs;
    float vy = (float)player->m_yVelocity / 15.f;
    extra[0] = std::clamp(flipped ? -vy : vy, -2.f, 2.f);
    extra[1] = player->m_isOnGround ? 1.f : 0.f;
    extra[2] = flipped ? 1.f : 0.f;
    extra[3] = player->m_playerSpeed;
    extra[4] = player->m_vehicleSize < 1.f ? 1.f : 0.f;
    extra[5] = dual ? 1.f : 0.f;
}
