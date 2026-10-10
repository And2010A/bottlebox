#pragma once

#include "Brain.hpp"

#include <vector>

class GJBaseGameLayer;
class GameObject;
class PlayerObject;

namespace aibot {

int modeOf(PlayerObject* player);

// Turns the level around a player into the grid the networks read.
class Sensors {
public:
    void clear();
    // Collects the objects that matter (solids, hazards, orbs, pads).
    // Cheap to call every attempt: only rebuilds when the level changed.
    void prepare(GJBaseGameLayer* layer);
    void observe(PlayerObject* player, bool holding, bool dual, float* out) const;

private:
    struct Entry {
        float x;
        GameObject* object;
        int channel;
    };
    std::vector<Entry> m_entries;
    GJBaseGameLayer* m_layer = nullptr;
    unsigned int m_objectCount = 0;
};

}
