

import fullcontrol.gcode as gc
import fullcontrol.visualize as vis


# The user-facing step classes. A design (list of these) is consumed by the gcode and
# visualize backends, which dispatch on each step's type via their renderers - so these
# classes carry only data (+ a few emission helpers), not backend methods.
#  - dual-backend concepts inherit from both the gcode and visualize subclasses;
#  - gcode-only / visualize-only concepts just re-expose the relevant backend class.
# A drift-guard test (tests/unit/test_architecture.py) ensures every backend class is
# exposed here and has a renderer.

# 1. concepts defined in both the gcode and visualize subpackages

class Point(gc.Point, vis.Point):
    '''
    Represents the x, y, z position of the nozzle.

    If any of the x, y, or z coordinates are not defined, the nozzle will not move in that direction.

    Optionally, for visualization purposes, the color can be defined as [r, g, b] where each value is in the range of 0-1.
    See the PlotControls documentation for the 'color_type' parameter.

    Attributes:
        x (float): The x-coordinate of the nozzle position.
        y (float): The y-coordinate of the nozzle position.
        z (float): The z-coordinate of the nozzle position.
        color (list): The color of the nozzle for visualization purposes.

    '''
    pass


class Extruder(gc.Extruder, vis.Extruder):
    '''
    Represents an extruder in a 3D printer.

    This class is used to manage the state of the extruder and translate the design into GCode.

    Attributes:
        on (bool): The state of the extruder. Set to True for on and False for off.
        units (str, optional): The units for E in GCode. Options include 'mm' and 'mm3'. If not specified, a default unit is used.
        dia_feed (float, optional): The diameter of the feedstock filament.
        relative_gcode (bool, optional): A flag indicating whether to use relative GCode. If not specified, a default value is used.

    Note:
        For more information about other attributes, please refer to the documentation.
    '''
    pass


class ExtrusionGeometry(gc.ExtrusionGeometry, vis.ExtrusionGeometry):
    """
    Represents the geometric description of the printed extrudate.

    This class is used to define the cross-sectional area of the extrudate based on the specified 'area_model'. The 'area' attribute is automatically calculated unless 'area_model' is set to 'manual'.

    Attributes:
        area_model (str, optional): The model used to define the cross-sectional area. Options include 'rectangle', 'stadium', 'circle', and 'manual'. If not specified, a default model is used.
        width (float, optional): The width of the printed line. Required if 'area_model' is 'rectangle' or 'stadium'.
        height (float, optional): The height of the printed line. Required if 'area_model' is 'rectangle' or 'stadium'.
        diameter (float, optional): The diameter of the printed line. Required if 'area_model' is 'circle'.
        area (float, optional): The cross-sectional area of the extrudate. Automatically calculated based on 'area_model' and relevant attributes unless 'area_model' is 'manual'.
    """
    pass

# 2. concepts defined in the gcode subpackage only


class PrinterCommand(gc.PrinterCommand):
    """
    Represents a command to be executed by a printer.

    This class is used to encapsulate a printer command, which can be 
    identified by a unique id.

    Attributes:
        id (type): A unique identifier for the command.
    """
    pass


class ManualGcode(gc.ManualGcode):
    """
    Custom Gcode class that allows adding a new line of Gcode defined by the 'text' attribute.

    Attributes:
        text (str): The custom Gcode line to be added.
    """
    pass


class Printer(gc.Printer):
    '''
    A class that represents a 3D printer.

    Attributes:
        print_speed (float): The speed at which the printer prints.
        travel_speed (float): The speed at which the printer moves between print locations.

    Note: For more information about other attributes, please refer to the documentation.
    '''
    pass


class Fan(gc.Fan):
    '''
    This class represents a generic fan component

    Attributes:
        speed_percent (float): The speed of the fan as a percentage (0-100).
    '''
    pass


class Hotend(gc.Hotend):
    '''
A class representing a generic hotend.

Attributes:
    temp (int): The temperature of the hotend.
    wait (bool): A flag indicating whether to wait for the hotend to reach the desired temperature.
    tool (int, optional): The tool number associated with the hotend. If not specified, no tool number will appear in gcode.

    '''
    pass


class Buildplate(gc.Buildplate):
    '''
    This class represents a build plate used in 3D printing.

    Attributes:
        temp (int): The temperature of the build plate.
        wait (bool): A flag indicating whether to wait for the build plate to reach the desired temperature.

    '''
    pass


class StationaryExtrusion(gc.StationaryExtrusion):
    """
    Represents stationary extrusion in a 3D printer.

    This class is used to manage and control the extrusion of a specific volume of material at a set speed while the printer's nozzle is stationary. Negative volumes indicate retraction.

    Attributes:
        volume(float): The volume of material to extrude. Negative values indicate retraction.
        speed(int): The speed at which to extrude the material - the units depend on the gcode format used but are typically mm/min.
    """
    pass


class GcodeComment(gc.GcodeComment):
    '''
    A class that represents a Gcode comment.

    Attributes:
        text (str): The comment text to be added as a new line of Gcode.
        end_of_previous_line_text (str): The comment text to be added at the end of the line of Gcode produced by the previous step.
    '''
    pass


class GcodeControls(gc.GcodeControls):
    '''
    Control to adjust the style and initialization of the gcode.

    Attributes:
        printer_name (Optional[str]): The name of the printer. Defaults to 'generic'.
        initialization_data (Optional[dict]): Values passed for initialization_data overwrite the default initialization_data of the printer. Defaults to an empty dictionary.
        save_as (Optional[str]): The file name to save the gcode as. Defaults to None resulting in no file being saved.
        include_date (Optional[bool]): Whether to include the date in the filename. Defaults to True.
    '''
    pass

# 3. concepts defined in the visualize subpackage only


class PlotAnnotation(vis.PlotAnnotation):
    '''
    Represents an annotation for a plot.

    Attributes:
        point (Optional[Point]): The xyz point associated with the annotation. If not defined, the previous point in the list of steps before this annotation was defined is used.
        label (Optional[str]): The label text to be shown on the plot.

    '''
    pass


class PlotControls(vis.PlotControls):
    """
    Control class to adjust the style of the plot.

    Attributes:
        color_type (Optional[str]): The type of color gradient to use. Default is 'z_gradient'. Options are 'manual', 'random_blue', 'z_gradient', 'print_sequence' and 'print_sequence_fluctuating'
        line_width (Optional[float]): The width of the lines in the plot. Default is 2.
        style (Optional[str]): The style of the plot. Can be 'tube' or 'line'. Default is None.
        tube_type (Optional[str]): The type of tube to use. Can be 'flow' or 'cylinders'. Default is 'flow'.
        tube_sides (Optional[int]): The number of sides of the tube. Default is 4.
        zoom (Optional[float]): The zoom level of the plot. Default is 1.
        hide_annotations (Optional[bool]): Whether to hide annotations in the plot. Default is False.
        hide_travel (Optional[bool]): Whether to hide travel lines in the plot. Default is False.
        hide_axes (Optional[bool]): Whether to hide axes in the plot. Default is False.
        neat_for_publishing (Optional[bool]): Whether to optimize the plot for publishing. Default is False.
        raw_data (Optional[bool]): Whether to show raw data in the plot. Default is False.
        printer_name (Optional[str]): The name of the printer. Default is 'generic'.
        initialization_data (Optional[dict]): Information about initial printing conditions. Default is an empty dictionary. Values passed for initialization_data overwrite the default initialization_data of the printer.
    """
    pass
