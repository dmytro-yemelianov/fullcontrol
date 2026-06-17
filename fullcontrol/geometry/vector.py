from fullcontrol.core.base import BaseModelPlus


class Vector(BaseModelPlus):
    """A vector defined by x, y, and z distances.

    Attributes:
        x (Optional[float]): The x distance of the vector.
        y (Optional[float]): The y distance of the vector.
        z (Optional[float]): The z distance of the vector.
    """
    x: float | None = None
    y: float | None = None
    z: float | None = None
