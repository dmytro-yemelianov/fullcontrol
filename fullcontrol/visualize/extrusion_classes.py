
from fullcontrol.common import Extruder as BaseExtruder
from fullcontrol.common import ExtrusionGeometry as BaseExtrusionGeometry


class Extruder(BaseExtruder):
    'Extruder on/off state (visualisation handled by the renderer)'


class ExtrusionGeometry(BaseExtrusionGeometry):
    'Extrusion cross-section (visualisation handled by the renderer)'

    
