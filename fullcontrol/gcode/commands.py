
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
