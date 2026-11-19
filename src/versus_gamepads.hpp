#pragma once
#include "native_match.hpp"
#include <SDL3/SDL.h>
#include <array>
#include <memory>

namespace ss6 {

// The original default preset (178e50) binds the physical buttons before
// 177310 expands the three configurable chords. Preserve separate chord
// bits so holding one slash while pressing a shoulder registers both edges.
inline uint32_t versusButton(SDL_GamepadButton button) {
    switch(button) {
    case SDL_GAMEPAD_BUTTON_DPAD_UP: return PadUp;
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN: return PadDown;
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT: return PadLeft;
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT: return PadRight;
    case SDL_GAMEPAD_BUTTON_WEST: return PadLight;
    case SDL_GAMEPAD_BUTTON_NORTH: return PadMedium;
    case SDL_GAMEPAD_BUTTON_EAST: return PadHeavy;
    case SDL_GAMEPAD_BUTTON_SOUTH: return PadKick;
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return PadSystem;
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return PadLightMedium;
    case SDL_GAMEPAD_BUTTON_START: return PadStart;
    default: return 0;
    }
}

class VersusGamepads {
    using Gamepad = std::unique_ptr<SDL_Gamepad, decltype(&SDL_CloseGamepad)>;
    std::array<Gamepad,2> devices_{{{nullptr,SDL_CloseGamepad},{nullptr,SDL_CloseGamepad}}};
    std::array<uint32_t,2> held_{};

    static uint32_t trigger(SDL_GamepadAxis axis) {
        if(axis==SDL_GAMEPAD_AXIS_LEFT_TRIGGER)return PadLightKick;
        if(axis==SDL_GAMEPAD_AXIS_RIGHT_TRIGGER)return PadMediumHeavy;
        return 0;
    }
    // SDL exposes the triggers as analog axes. Half travel gives each one
    // a digital press/release like the two PS2 trigger buttons.
    static bool pressed(Sint16 value) {return value>=16384;}
    static uint32_t read(SDL_Gamepad* pad) {
        uint32_t held=0;
        for(int b=0;b<SDL_GAMEPAD_BUTTON_COUNT;++b) {
            const auto button=static_cast<SDL_GamepadButton>(b);
            if(SDL_GetGamepadButton(pad,button))held|=versusButton(button);
        }
        for(auto axis:{SDL_GAMEPAD_AXIS_LEFT_TRIGGER,SDL_GAMEPAD_AXIS_RIGHT_TRIGGER})
            if(pressed(SDL_GetGamepadAxis(pad,axis)))held|=trigger(axis);
        return held;
    }
    void attach(SDL_JoystickID id) {
        for(const auto& pad:devices_)if(pad&&SDL_GetGamepadID(pad.get())==id)return;
        for(unsigned i=0;i<devices_.size();++i)if(!devices_[i]) {
            devices_[i].reset(SDL_OpenGamepad(id));
            if(devices_[i])held_[i]=read(devices_[i].get());
            return;
        }
    }
    void scan() {
        int count=0;
        auto* ids=SDL_GetGamepads(&count);
        for(int i=0;i<count;++i)attach(ids[i]);
        SDL_free(ids);
    }
public:
    VersusGamepads() {scan();}
    const std::array<uint32_t,2>& held() const {return held_;}
    void event(const SDL_Event& e) {
        if(e.type==SDL_EVENT_GAMEPAD_ADDED){attach(e.gdevice.which);return;}
        SDL_JoystickID id=0;
        uint32_t bit=0;
        bool down=false;
        switch(e.type) {
        case SDL_EVENT_GAMEPAD_REMOVED:
        case SDL_EVENT_GAMEPAD_REMAPPED: id=e.gdevice.which;break;
        case SDL_EVENT_GAMEPAD_AXIS_MOTION:
            id=e.gaxis.which;bit=trigger(static_cast<SDL_GamepadAxis>(e.gaxis.axis));down=pressed(e.gaxis.value);break;
        case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
        case SDL_EVENT_GAMEPAD_BUTTON_UP:
            id=e.gbutton.which;bit=versusButton(static_cast<SDL_GamepadButton>(e.gbutton.button));
            down=e.type==SDL_EVENT_GAMEPAD_BUTTON_DOWN;break;
        default: return;
        }
        for(unsigned i=0;i<devices_.size();++i) {
            auto& pad=devices_[i];
            if(!pad||SDL_GetGamepadID(pad.get())!=id)continue;
            if(e.type==SDL_EVENT_GAMEPAD_REMAPPED)held_[i]=read(pad.get());
            else if(e.type==SDL_EVENT_GAMEPAD_REMOVED) {
                // Keep the other player's side stable when a pad leaves.
                pad.reset();held_[i]=0;scan();
            } else if(down)held_[i]|=bit;
            else held_[i]&=~bit;
            return;
        }
    }
};
} // namespace ss6
