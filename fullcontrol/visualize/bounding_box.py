from pydantic import BaseModel

from fullcontrol.common import Point, Arc
from fullcontrol.core.arc import arc_geometry, arc_points


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
        # running position so an Arc (which bulges beyond its end point) can be expanded
        # into the points it sweeps through from the current position
        cur_x = cur_y = cur_z = None

        def include(x, y, z):
            nonlocal foundx, foundy, foundz
            if x is not None:
                self.minx, self.maxx = (min(self.minx, x), max(self.maxx, x)) if foundx else (x, x)
                foundx = True
            if y is not None:
                self.miny, self.maxy = (min(self.miny, y), max(self.maxy, y)) if foundy else (y, y)
                foundy = True
            if z is not None:
                self.minz, self.maxz = (min(self.minz, z), max(self.maxz, z)) if foundz else (z, z)
                foundz = True

        for step in steps:
            if isinstance(step, Arc):
                if cur_x is not None and cur_y is not None:
                    geom = arc_geometry(step, cur_x, cur_y, cur_z)
                    for px, py, pz in arc_points(step, cur_x, cur_y, cur_z, geom):
                        include(px, py, pz)
                cur_x = step.end.x if step.end.x is not None else cur_x
                cur_y = step.end.y if step.end.y is not None else cur_y
                cur_z = step.end.z if step.end.z is not None else cur_z
            elif isinstance(step, Point):
                if step.x is not None:
                    cur_x = step.x
                if step.y is not None:
                    cur_y = step.y
                if step.z is not None:
                    cur_z = step.z
                include(step.x, step.y, step.z)
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
