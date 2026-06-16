from pydantic import BaseModel
from typing import TYPE_CHECKING
# from fullcontrol.vis_OO2.color import PathColors, Color
from fullcontrol.common import Extruder

if TYPE_CHECKING:
    from fullcontrol.visualize.state import State


class Path(BaseModel):
    """
    A class representing a path to be plotted.

    Attributes:
        xvals (Optional[list]): List of x-values for the line.
        yvals (Optional[list]): List of y-values for the line.
        zvals (Optional[list]): List of z-values for the line.
        colors (Optional[list]): List of [r, g, b] values for the line color.
        extruder (Optional[Extruder]): Information about the extruder state for the path.
        widths (Optional[list]): List of widths for the line.
        heights (Optional[list]): List of heights for the line.
    """

    xvals: list | None = []
    yvals: list | None = []
    zvals: list | None = []
    colors: list | None = []  # [r,g,b]
    extruder: Extruder | None = None
    widths: list | None = []
    heights: list | None = []

    def add_point(self, state: 'State'):
        """
        Append a point to this path.

        Args:
            state ('State'): The state containing the point to be added.
        """
        self.xvals.append(state.point.x)
        self.yvals.append(state.point.y)
        self.zvals.append(state.point.z)
        self.colors.append(state.point.color)
        self.widths.append(state.extrusion_geometry.width)
        self.heights.append(state.extrusion_geometry.height)
