
# import classes
from fullcontrol.core.point import Point
from fullcontrol.core.extrusion_classes import Extruder
# geometry is backend-free: it builds designs from the core data classes, which are directly
# renderable by every backend (see fullcontrol/gcode/renderers.py). The geometry submodules
# import these from here, so this is the single place those classes are chosen.
from fullcontrol.geometry.vector import Vector
from fullcontrol.geometry.polar import PolarPoint

# import functions
from fullcontrol.geometry.polar import point_to_polar, polar_to_point, polar_to_vector
from fullcontrol.geometry.midpoint import midpoint, interpolated_point, centreXY_3pt
# , distance_forgiving
from fullcontrol.geometry.measure import distance, angleXY_between_3_points, path_length
from fullcontrol.geometry.move import move
from fullcontrol.geometry.move_polar import move_polar
from fullcontrol.geometry.reflect import reflectXY, reflectXY_mc
from fullcontrol.geometry.reflect_polar import reflectXYpolar
from fullcontrol.geometry.ramping import ramp_xyz, ramp_polar
from fullcontrol.geometry.arcs import arcXY, variable_arcXY, elliptical_arcXY, arcXY_3pt
from fullcontrol.geometry.shapes import rectangleXY, circleXY, circleXY_3pt, ellipseXY, polygonXY, spiralXY, helixZ
from fullcontrol.geometry.waves import squarewaveXY, squarewaveXYpolar, trianglewaveXYpolar, sinewaveXYpolar
from fullcontrol.geometry.segmentation import segmented_line, segmented_path
from fullcontrol.geometry.travel_to import travel_to

# Point and Extruder are imported above only so the geometry submodules build designs from the
# core data classes; they are deliberately NOT re-exported via `import *` - the public
# fc.Point / fc.Extruder are the combined backend classes assembled in the combinations layer.
# (explicit `from fullcontrol.geometry import Point` still works for the submodules.)
__all__ = [_n for _n in dir() if not _n.startswith('_') and _n not in ('Point', 'Extruder')]
