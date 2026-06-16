
from fullcontrol.common import BaseModelPlus


class PrinterCommand(BaseModelPlus):
    """
    Represents a printer command that should be executed, manifesting in an appropriate line of gcode.

    Attributes:
        id (Optional[str]): The ID of the printer command that should be executed.
    """

    id: str | None = None


class ManualGcode(BaseModelPlus):
    """
    Represents custom gcode defined by the 'text' attribute.

    Attributes:
        text (Optional[str]): The custom gcode text to be added as a new line of gcode.
    """
    text: str | None = None


class Acceleration(BaseModelPlus):
    """Set the printer's maximum acceleration (M204).

    M204 is portable across Marlin / Klipper / RepRap-Duet, so this is a
    flavor-independent step object. Whichever of the print / retract / travel values are
    set are emitted (in mm/s^2); fields left None are omitted. Firmware-specific tuning
    (jerk M205, pressure advance) is intentionally not handled here.

    Attributes:
        printing (Optional[float]): acceleration for extruding moves (M204 P).
        retract (Optional[float]): acceleration for retract/unretract moves (M204 R).
        travel (Optional[float]): acceleration for travel moves (M204 T).
    """
    printing: float | None = None
    retract: float | None = None
    travel: float | None = None
