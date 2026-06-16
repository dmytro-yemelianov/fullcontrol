from fullcontrol.common import BaseModelPlus


class Fan(BaseModelPlus):
    '''
    Represents a fan with a speed percentage.

    Attributes:
        speed_percent (Optional[int]): The speed of the fan as a percentage (0-100).
    '''
    speed_percent: int | None = None


class Hotend(BaseModelPlus):
    '''
    Represents a hotend component.

    Attributes:
        temp (Optional[int]): The temperature of the hotend.
        wait (Optional[bool]): If True, the system will wait for the temperature to be reached before continuing.
        tool (Optional[int]): The tool number for multi-tool printers.
    '''
    temp: int | None = None
    wait: bool | None = False
    tool: int | None = None


class Buildplate(BaseModelPlus):
    """Represents a buildplate.

    Args:
        temp (Optional[int]): The temperature of the buildplate.
        wait (Optional[bool]): If True, the system will wait for the temperature to be reached before continuing.
    """
    temp: int | None = None
    wait: bool | None = False
