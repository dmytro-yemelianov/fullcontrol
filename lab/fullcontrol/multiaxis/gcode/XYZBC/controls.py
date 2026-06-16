
from typing import Optional
from pydantic import BaseModel
from fullcontrol.common import Point


class GcodeControls(BaseModel):
    'control to adjust the style and initialization of the gcode'
    bc_intercept: Point | None = Point(x=0, y=0, z=0)
    initialization_data: dict | None = {}  # values passed for initialization_data overwrite the default initialization_data of the printer
    save_as: str | None = None
