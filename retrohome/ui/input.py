"""Unified input: gamepads (SDL GameController + raw joystick fallback) and keyboard.

Produces simple action strings: up down left right a b x y lb rb start select
(Xbox layout: A = confirm/bottom, B = back/right - matches Steam Deck.)
"""
import pygame

UP, DOWN, LEFT, RIGHT = "up", "down", "left", "right"
DIRS = (UP, DOWN, LEFT, RIGHT)

KEYMAP = {
    pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT,
    pygame.K_RETURN: "a", pygame.K_KP_ENTER: "a", pygame.K_ESCAPE: "b",
    pygame.K_PAGEUP: "lb", pygame.K_PAGEDOWN: "rb", pygame.K_F1: "start", pygame.K_TAB: "select",
}
LETTER_KEYMAP = {  # only active when not typing into a text field
    pygame.K_w: UP, pygame.K_s: DOWN, pygame.K_a: LEFT, pygame.K_d: RIGHT,
    pygame.K_SPACE: "a", pygame.K_BACKSPACE: "b", pygame.K_x: "x", pygame.K_y: "y",
    pygame.K_q: "lb", pygame.K_e: "rb", pygame.K_m: "start",
}
# Raw joystick fallback (Xbox / XInput / Steam virtual pad order)
JOY_BUTTONS = {0: "a", 1: "b", 2: "x", 3: "y", 4: "lb", 5: "rb", 6: "select", 7: "start"}

REPEAT_DELAY = 0.38
REPEAT_RATE = 0.075
FAST_AFTER = 1.6
FAST_RATE = 0.03
AXIS_ON = 0.55
AXIS_OFF = 0.35


class Input:
    def __init__(self):
        pygame.joystick.init()
        self.ctrl = None
        try:
            from pygame._sdl2 import controller as ctrl
            ctrl.init()
            self.ctrl = ctrl
        except Exception:  # noqa: BLE001
            self.ctrl = None
        self.controllers = {}   # device index -> Controller
        self.joysticks = {}     # instance id -> Joystick (only devices that aren't GameControllers)
        self.held = {}          # source -> direction
        self.hold_time = 0.0
        self.next_repeat = 0.0
        self.cur_dir = None
        self.text_mode = False
        self.last_device = "keyboard"
        self.pad_family = "xbox"        # family of the controller used most recently (for button labels)
        self.families = {}              # joystick instance id -> family
        self.enabled = True
        for i in range(pygame.joystick.get_count()):
            self._add_device(i)

    # ------------------------------------------------------------ devices
    def _note_family(self, idx):
        from ..padstyle import family_from_name
        name = ""
        try:
            name = self.ctrl.name_forindex(idx) if self.ctrl else ""
        except Exception:  # noqa: BLE001
            pass
        try:
            j = pygame.joystick.Joystick(idx)
            name = name or j.get_name()
            fam = family_from_name(name)
            self.families[j.get_instance_id()] = fam
            self.pad_family = fam
        except Exception:  # noqa: BLE001
            if name:
                self.pad_family = family_from_name(name)

    def _add_device(self, idx):
        self._note_family(idx)
        try:
            if self.ctrl and self.ctrl.is_controller(idx):
                if idx not in self.controllers:
                    self.controllers[idx] = self.ctrl.Controller(idx)
                return
        except Exception:  # noqa: BLE001 - fall back to raw joystick below
            self.controllers.pop(idx, None)
        try:
            j = pygame.joystick.Joystick(idx)
            j.init()
            self.joysticks[j.get_instance_id()] = j
        except Exception:  # noqa: BLE001
            pass

    def _remove_device(self, instance_id):
        self.joysticks.pop(instance_id, None)
        for k, c in list(self.controllers.items()):
            try:
                if not c.attached():
                    c.quit()
                    self.controllers.pop(k, None)
            except Exception:  # noqa: BLE001
                self.controllers.pop(k, None)
        self.held.clear()

    @property
    def pad_count(self):
        return len(self.controllers) + len(self.joysticks)

    # ------------------------------------------------------------ events
    def process(self, event):
        """Return a list of actions for this event."""
        t = event.type
        out = []
        if t == pygame.JOYDEVICEADDED:
            self._add_device(event.device_index)
            return out
        if t == pygame.JOYDEVICEREMOVED:
            self._remove_device(getattr(event, "instance_id", -1))
            return out
        if not self.enabled:
            return out

        if t == pygame.KEYDOWN:
            self.last_device = "keyboard"
            a = KEYMAP.get(event.key)
            if a is None and not self.text_mode:
                a = LETTER_KEYMAP.get(event.key)
            if a:
                if a in DIRS:
                    self._press_dir("kb", a, out)
                else:
                    out.append(a)
        elif t == pygame.KEYUP:
            a = KEYMAP.get(event.key) or LETTER_KEYMAP.get(event.key)
            if a in DIRS and self.held.get("kb") == a:
                self._release("kb")

        # ---- SDL GameController (standardised layout) ----
        elif self.ctrl and t == getattr(pygame, "CONTROLLERBUTTONDOWN", -1):
            self.last_device = "pad"
            self.pad_family = self.families.get(getattr(event, "instance_id", None), self.pad_family)
            a = self._ctrl_button(event.button)
            if a in DIRS:
                self._press_dir(("cb", a), a, out)
            elif a:
                out.append(a)
        elif self.ctrl and t == getattr(pygame, "CONTROLLERBUTTONUP", -1):
            a = self._ctrl_button(event.button)
            if a in DIRS:
                self._release(("cb", a))
        elif self.ctrl and t == getattr(pygame, "CONTROLLERAXISMOTION", -1):
            v = event.value / 32767.0 if abs(event.value) > 1.5 else event.value
            if event.axis == pygame.CONTROLLER_AXIS_LEFTX:
                self._axis(("ca", event.instance_id if hasattr(event, "instance_id") else 0, "x"), v, LEFT, RIGHT, out)
            elif event.axis == pygame.CONTROLLER_AXIS_LEFTY:
                self._axis(("ca", event.instance_id if hasattr(event, "instance_id") else 0, "y"), v, UP, DOWN, out)

        # ---- raw joystick fallback (ignored for devices opened as controllers) ----
        elif t == pygame.JOYBUTTONDOWN and event.instance_id in self.joysticks:
            self.last_device = "pad"
            self.pad_family = self.families.get(event.instance_id, self.pad_family)
            a = JOY_BUTTONS.get(event.button)
            if a:
                out.append(a)
        elif t == pygame.JOYHATMOTION and event.instance_id in self.joysticks:
            x, y = event.value
            src = ("hat", event.instance_id)
            if x == 0 and y == 0:
                self._release(src)
            else:
                self._press_dir(src, LEFT if x < 0 else RIGHT if x > 0 else UP if y > 0 else DOWN, out)
        elif t == pygame.JOYAXISMOTION and event.instance_id in self.joysticks and event.axis in (0, 1):
            src = ("ja", event.instance_id, event.axis)
            if event.axis == 0:
                self._axis(src, event.value, LEFT, RIGHT, out)
            else:
                self._axis(src, event.value, UP, DOWN, out)
        return out

    def _ctrl_button(self, b):
        P = pygame
        m = {
            P.CONTROLLER_BUTTON_A: "a", P.CONTROLLER_BUTTON_B: "b",
            P.CONTROLLER_BUTTON_X: "x", P.CONTROLLER_BUTTON_Y: "y",
            P.CONTROLLER_BUTTON_LEFTSHOULDER: "lb", P.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb",
            P.CONTROLLER_BUTTON_START: "start", P.CONTROLLER_BUTTON_BACK: "select",
            P.CONTROLLER_BUTTON_GUIDE: "guide",
            P.CONTROLLER_BUTTON_DPAD_UP: UP, P.CONTROLLER_BUTTON_DPAD_DOWN: DOWN,
            P.CONTROLLER_BUTTON_DPAD_LEFT: LEFT, P.CONTROLLER_BUTTON_DPAD_RIGHT: RIGHT,
        }
        return m.get(b)

    def _axis(self, src, v, neg, pos, out):
        cur = self.held.get(src)
        if v <= -AXIS_ON:
            if cur != neg:
                self.last_device = "pad"
                self._press_dir(src, neg, out)
        elif v >= AXIS_ON:
            if cur != pos:
                self.last_device = "pad"
                self._press_dir(src, pos, out)
        elif abs(v) < AXIS_OFF and cur:
            self._release(src)

    def _press_dir(self, src, d, out):
        self.held[src] = d
        self.cur_dir = d
        self.hold_time = 0.0
        self.next_repeat = REPEAT_DELAY
        out.append(d)

    def _release(self, src):
        self.held.pop(src, None)
        if not self.held:
            self.cur_dir = None
        else:
            self.cur_dir = list(self.held.values())[-1]

    def update(self, dt):
        """Key-repeat for held directions. Returns list of actions."""
        if not self.cur_dir or not self.enabled:
            return []
        self.hold_time += dt
        out = []
        while self.hold_time >= self.next_repeat:
            out.append(self.cur_dir)
            self.next_repeat += FAST_RATE if self.hold_time > FAST_AFTER else REPEAT_RATE
            if len(out) > 3:
                self.next_repeat = self.hold_time + REPEAT_RATE
                break
        return out

    def reset(self):
        self.held.clear()
        self.cur_dir = None
