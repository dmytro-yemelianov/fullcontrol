from pydantic import BaseModel
from typing import Optional

from fullcontrol.common import Point


class BoundingBox(BaseModel):
    '''
    Represents the geometric measures of a bounding box, including mid values and ranges.

    Attributes:
        minx (Optional[float]): The minimum x-coordinate of the bounding box.
        midx (Optional[float]): The mid x-coordinate of the bounding box.
        maxx (Optional[float]): The maximum x-coordinate of the bounding box.
        rangex (Optional[float]): The range of x-coordinates in the bounding box.
        miny (Optional[float]): The minimum y-coordinate of the bounding box.
        midy (Optional[float]): The mid y-coordinate of the bounding box.
        maxy (Optional[float]): The maximum y-coordinate of the bounding box.
        rangey (Optional[float]): The range of y-coordinates in the bounding box.
        minz (Optional[float]): The minimum z-coordinate of the bounding box.
        midz (Optional[float]): The mid z-coordinate of the bounding box.
        maxz (Optional[float]): The maximum z-coordinate of the bounding box.
        rangez (Optional[float]): The range of z-coordinates in the bounding box.
    '''

    minx: float | None = None
    midx: float | None = None
    maxx: float | None = None
    # ranges and mid values are included as attributes, even though they are simple, to avoid them
    # being calculated for every point for the color_type z_gradient
    rangex: float | None = None
    miny: float | None = None
    midy: float | None = None
    maxy: float | None = None
    rangey: float | None = None
    minz: float | None = None
    midz: float | None = None
    maxz: float | None = None
    rangez: float | None = None

    def calc_bounds(self, steps):
        '''
        Calculate the bounds and other useful geometric measures of the bounding box for all points in a list of steps.

        Args:
            steps (List[Point]): A list of points representing the steps.

        Returns:
            None
        '''
        # track per-axis so a design with no points (or a missing axis) yields a
        # zero range rather than a sentinel-derived negative one
        foundx = foundy = foundz = False
        for step in steps:
            if isinstance(step, Point):
                if (x := step.x) is not None:
                    self.minx, self.maxx = (min(self.minx, x), max(self.maxx, x)) if foundx else (x, x)
                    foundx = True
                if (y := step.y) is not None:
                    self.miny, self.maxy = (min(self.miny, y), max(self.maxy, y)) if foundy else (y, y)
                    foundy = True
                if (z := step.z) is not None:
                    self.minz, self.maxz = (min(self.minz, z), max(self.maxz, z)) if foundz else (z, z)
                    foundz = True
        if not foundx:
            self.minx = self.maxx = 0
        if not foundy:
            self.miny = self.maxy = 0
        if not foundz:
            self.minz = self.maxz = 0
        self.midx = (self.minx + self.maxx) / 2
        self.midy = (self.miny + self.maxy) / 2
        self.midz = (self.minz + self.maxz) / 2
        self.rangex = (self.maxx - self.minx)
        self.rangey = (self.maxy - self.miny)
        self.rangez = (self.maxz - self.minz)
