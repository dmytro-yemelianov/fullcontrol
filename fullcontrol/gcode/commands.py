
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


class Jerk(BaseModelPlus):
    """Set the printer's maximum jerk / instantaneous speed change (Marlin M205).

    Jerk is firmware-specific (Marlin classic jerk; Klipper uses square_corner_velocity),
    so the emitted command goes through the gcode flavor. Whichever axes are set are emitted.

    Attributes:
        x, y, z, e (Optional[float]): per-axis jerk (mm/s); axes left None are omitted.
    """
    x: float | None = None
    y: float | None = None
    z: float | None = None
    e: float | None = None


class PressureAdvance(BaseModelPlus):
    """Set pressure / linear advance (Marlin M900 K).

    Compensates for pressure build-up in the nozzle. The command is firmware-specific
    (Marlin 'Linear Advance' M900 K; Klipper/Duet 'pressure advance'), so it goes through
    the gcode flavor.

    Attributes:
        value (Optional[float]): the advance factor (K). None emits nothing.
        tool (Optional[int]): optional tool number.
    """
    value: float | None = None
    tool: int | None = None
