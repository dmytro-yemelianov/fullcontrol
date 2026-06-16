from fullcontrol.core.base import BaseModelPlus


class Point(BaseModelPlus):
    """Represents a point in 3D space with x, y, and z cartesian components.

    color is a plain data attribute ([r, g, b], each 0-1) consumed by the visualize backend;
    the colouring logic lives there, but the field is on the core Point so backend-free code
    (e.g. the geometry generators) can produce colourable points.
    """
    x: float | None = None
    y: float | None = None
    z: float | None = None
    color: list | None = None
