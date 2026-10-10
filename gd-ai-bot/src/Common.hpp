#pragma once

namespace aibot {

// Game modes the bot knows about. Each one has its own feel for "how long
// to hold", and in Human mode its own neural network.
enum GameMode : int {
    Cube = 0,
    Ship,
    Ball,
    Ufo,
    Wave,
    Robot,
    Spider,
    Swing,
    ModeCount,
};

inline char const* modeName(int mode) {
    switch (mode) {
        case Cube: return "Cube";
        case Ship: return "Ship";
        case Ball: return "Ball";
        case Ufo: return "UFO";
        case Wave: return "Wave";
        case Robot: return "Robot";
        case Spider: return "Spider";
        case Swing: return "Swing";
        default: return "?";
    }
}

// GD physics runs at 240 ticks per second.
constexpr int kTicksPerSecond = 240;

}
