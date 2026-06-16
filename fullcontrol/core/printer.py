from fullcontrol.core.base import BaseModelPlus


class Printer(BaseModelPlus):
    """
    A class representing a 3D printer.

    Attributes:
        print_speed (Optional[int]): The speed at which the printer prints, in units per minute.
        travel_speed (Optional[int]): The speed at which the printer moves between printing locations, in units per minute.
    """
    print_speed: float | None = None
    travel_speed: float | None = None
