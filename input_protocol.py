"""Validate untrusted input and release held keys/buttons on every disconnect."""
import math

BUTTONS = {0: 0x110, 1: 0x112, 2: 0x111}


def number(data, name, default=None):
    value = data.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return value


def down_value(data):
    value = data.get('down')
    if type(value) is not bool:
        raise ValueError('down must be a boolean')
    return value


class InputState:
    def __init__(self, host, width, height):
        self.host, self.width, self.height = host, width, height
        self.keys, self.buttons = set(), set()

    def handle(self, data):
        if not isinstance(data, dict):
            raise ValueError('Input message must be a JSON object')
        typ = data.get('type')
        if typ == 'release':
            self.release()
        elif typ == 'move':
            x = max(0.0, min(number(data, 'x'), self.width - 1))
            y = max(0.0, min(number(data, 'y'), self.height - 1))
            self.host.notify('NotifyPointerMotionAbsolute', '(sdd)', (self.host.STREAM_PATH, x, y))
        elif typ == 'button':
            button = data.get('button')
            if type(button) is not int or button not in BUTTONS:
                raise ValueError('button must be 0, 1 or 2')
            down = down_value(data)
            if down:
                self.buttons.add(button)
            else:
                self.buttons.discard(button)
            self.host.notify('NotifyPointerButton', '(ib)', (BUTTONS[button], down))
        elif typ == 'wheel':
            dx = max(-10000, min(number(data, 'dx', 0), 10000)) / 10.0
            dy = max(-10000, min(number(data, 'dy', 0), 10000)) / 10.0
            self.host.notify('NotifyPointerAxis', '(ddu)', (dx, dy, 2))
        elif typ == 'key':
            key = data.get('key')
            if not isinstance(key, str) or len(key) > 32:
                raise ValueError('key must be a short string')
            down = down_value(data)
            ks = self.host.key_to_keysym(key)
            if ks is not None:
                if down:
                    if len(self.keys) >= 64 and ks not in self.keys:
                        raise ValueError('Too many held keys')
                    self.keys.add(ks)
                else:
                    self.keys.discard(ks)
                self.host.send_keysym(ks, down)
        elif typ == 'text':
            text = data.get('text')
            if not isinstance(text, str) or len(text) > 256:
                raise ValueError('text must contain at most 256 characters')
            for ch in text:
                key = 'Enter' if ch == '\n' else 'Tab' if ch == '\t' else ch
                ks = self.host.key_to_keysym(key)
                self.host.send_keysym(ks, True)
                self.host.send_keysym(ks, False)
        elif typ != 'ping':
            raise ValueError('Unknown input message type')

    def release(self):
        for ks in list(self.keys):
            self.host.send_keysym(ks, False)
        for button in list(self.buttons):
            self.host.notify('NotifyPointerButton', '(ib)', (BUTTONS[button], False))
        self.keys.clear()
        self.buttons.clear()
