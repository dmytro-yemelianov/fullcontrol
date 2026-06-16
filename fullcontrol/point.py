from typing import Optional
from fullcontrol.common import BaseModelPlus


class Point(BaseModelPlus):
    """Represents a point in 3D space with x, y, and z cartesian components."""
    x: float | None = None
    y: float | None = None
    z: float | None = None
