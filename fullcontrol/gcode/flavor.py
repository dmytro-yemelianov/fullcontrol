"""Gcode flavors (firmware dialects).

The renderers keep the *logic* of a design (state tracking, motion, extrusion maths) but
delegate the firmware-specific command vocabulary - hotend/bed temperature, fan, extrusion
mode, acceleration - to a GcodeFlavor. The default flavor is Marlin-style and is byte-for-byte
identical to the previously hardcoded output. Target another firmware by subclassing
GcodeFlavor, overriding the methods that differ, and registering it with register_flavor();
select it per design via initialization_data['gcode_flavor'].
"""
from fullcontrol.gcode.number_format import fmt

MAX_FAN_PWM = 255  # Marlin fan speed is an 8-bit PWM value (M106 S0-255)
PERCENT = 100


class GcodeFlavor:
    'Marlin-style gcode dialect (the default). Override individual methods for other firmwares.'
    name = 'marlin'

    def extrusion_mode(self, relative: bool) -> str:
        'M82/M83 (absolute/relative extrusion); absolute also zeroes the extrusion position.'
        return "M83 ; relative extrusion" if relative is True \
            else "M82 ; absolute extrusion\nG92 E0 ; reset extrusion position to zero"

    def fan(self, speed_percent: float) -> str:
        'Set fan speed (firmware-specific scaling lives here; Marlin uses 0-255 PWM).'
        return f'M106 S{int(speed_percent * MAX_FAN_PWM / PERCENT)} ; set fan speed'

    def hotend_temp(self, temp, wait: bool, tool) -> str:
        'M104 (set and continue) / M109 (set and wait), optionally for a specific tool.'
        if tool is None:
            return f'M104 S{temp} ; set hotend temp and continue' if wait is False \
                else f'M109 S{temp} ; set hotend temp and wait'
        return f'M104 S{temp} T{tool} ; set hotend temp for tool {tool} and continue' if wait is False \
            else f'M109 S{temp} T{tool} ; set hotend temp for tool {tool} and wait'

    def bed_temp(self, temp, wait: bool) -> str:
        'M140 (set and continue) / M190 (set and wait) for the build plate.'
        return f'M140 S{temp} ; set bed temp and continue' if wait is False \
            else f'M190 S{temp} ; set bed temp and wait'

    def acceleration(self, printing, retract, travel) -> str | None:
        'M204 P<print> R<retract> T<travel>, omitting any axis left unset.'
        parts = [f'{tag}{fmt(v)}' for tag, v in
                 (('P', printing), ('R', retract), ('T', travel)) if v is not None]
        if parts:
            return 'M204 ' + ' '.join(parts) + ' ; set acceleration'

    def jerk(self, x, y, z, e) -> str | None:
        'M205 X<j> Y<j> Z<j> E<j> (classic Marlin jerk), omitting any axis left unset.'
        parts = [f'{tag}{fmt(v)}' for tag, v in
                 (('X', x), ('Y', y), ('Z', z), ('E', e)) if v is not None]
        if parts:
            return 'M205 ' + ' '.join(parts) + ' ; set jerk'

    def pressure_advance(self, value, tool) -> str | None:
        'M900 K<factor> (Marlin Linear Advance), optionally for a specific tool.'
        if value is None:
            return None
        if tool is None:
            return f'M900 K{fmt(value)} ; set pressure advance'
        return f'M900 T{tool} K{fmt(value)} ; set pressure advance'


_FLAVORS = {}


def register_flavor(name: str, flavor_class: type) -> None:
    'Register a GcodeFlavor subclass under a name selectable via gcode_flavor config.'
    _FLAVORS[name] = flavor_class


def get_flavor(name: str) -> GcodeFlavor:
    'Return an instance of the named flavor; raises a clear error for an unknown name.'
    if name not in _FLAVORS:
        raise ValueError(
            f'unknown gcode flavor {name!r}. Available: {sorted(_FLAVORS)}. '
            'Register new flavors with register_flavor().')
    return _FLAVORS[name]()


register_flavor('marlin', GcodeFlavor)
