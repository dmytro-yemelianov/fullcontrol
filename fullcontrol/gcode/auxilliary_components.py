from fullcontrol.common import Fan as BaseFan
from fullcontrol.common import Hotend as BaseHotend
from fullcontrol.common import Buildplate as BaseBuildplate

MAX_FAN_PWM = 255  # gcode fan speed is an 8-bit PWM value (M106 S0-255)
PERCENT = 100


class Fan(BaseFan):
    'Fan speed control (gcode emission handled by the renderer)'


class Hotend(BaseHotend):
    'Hotend temperature control (gcode emission handled by the renderer)'


class Buildplate(BaseBuildplate):
    'Build-plate temperature control (gcode emission handled by the renderer)'
