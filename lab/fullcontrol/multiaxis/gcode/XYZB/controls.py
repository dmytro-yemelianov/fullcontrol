
from pydantic import BaseModel


class GcodeControls(BaseModel):
    'control to adjust the style and initialization of the gcode'
    # offset of axis-of-rotation relative to nozzle in x (positive if axis is in the positive x direction from the nozzle tip) when B=0
    b_offset_x: float | None = 0
    # offset of axis-of-rotation relative to nozzle in z (positive if axis is in the positive z direction from the nozzle tip) when B=0
    b_offset_z: float | None = None
    # values passed for initialization_data overwrite the default initialization_data of the printer
    initialization_data: dict | None = {}
    save_as: str | None = None
