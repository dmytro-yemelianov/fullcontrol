from fullcontrol.common import Point as BasePoint
from fullcontrol.gcode.number_format import fmt
from copy import deepcopy


class Point(BasePoint):
    'generic gcode Point with 4-axis aspects added/modified'
    b: float | None = None

    def XYZB_gcode(self, self_systemXYZ, p) -> str:
        'generate XYZBC gcode string to move from a point p to this point. return XYZB string'
        s = ''
        if self_systemXYZ.x is not None and self_systemXYZ.x != p.x:
            s += f'X{fmt(round(self_systemXYZ.x, 6))} '
        if self_systemXYZ.y is not None and self_systemXYZ.y != p.y:
            s += f'Y{fmt(round(self_systemXYZ.y, 6))} '
        if self_systemXYZ.z is not None and self_systemXYZ.z != p.z:
            s += f'Z{fmt(round(self_systemXYZ.z, 6))} '
        if self_systemXYZ.b is not None and self_systemXYZ.b != p.b:
            s += f'B{fmt(round(self_systemXYZ.b, 6))} '
        return s if s != '' else None

    def inverse_kinematics(self, state):
        'calculate system XYZ for the current point XYZ (in part coordinates)'

        def model2system(model_point, state, system_type: str):
            from math import cos, sin, radians
            system_point = deepcopy(model_point)
            if system_type == 'b_nozzle':
                # nozzle tilts about B; correct X/Z for the nozzle-tip offset
                # (b_offset_x/z) from the rotation axis so the tip stays on the model point
                b = radians(model_point.b)
                nozzle_offset_x, nozzle_offset_z = -state.printer.b_offset_x, -state.printer.b_offset_z
                nozzle_offset_from_b0_x = -(nozzle_offset_x*(1-cos(b))) + nozzle_offset_z*sin(b)
                nozzle_offset_from_b0_z = -(nozzle_offset_z*(1-cos(b))) + nozzle_offset_x*-sin(b)
                x_system = model_point.x - nozzle_offset_from_b0_x
                y_system = model_point.y
                z_system = model_point.z - nozzle_offset_from_b0_z

            system_point.x = round(x_system, 6)
            system_point.y = round(y_system, 6)
            system_point.z = round(z_system, 6)
            system_point.b = round(model_point.b, 6)
            return system_point

        # make sure undefined attributes of the current point (self) are taken from the point in state
        model_point = deepcopy(state.point)
        model_point.update_from(self)
        # inverse kinematics:
        system_point = model2system(model_point, state, 'b_nozzle')
        return system_point

    def gcode(self, state):
        'process this instance in a list of steps supplied by the designer to generate and return a line of gcode'
        self_systemXYZ = self.inverse_kinematics(state)
        XYZB_str = self.XYZB_gcode(self_systemXYZ, state.point_systemXYZ)
        if XYZB_str is not None:  # only write a line of gcode if movement occurs
            G_str = 'G1 ' if state.extruder.on else 'G0 '
            F_str = state.printer.f_gcode(state)
            E_str = state.extruder.e_gcode(self, state)
            gcode_str = f'{G_str}{F_str}{XYZB_str}{E_str}'
            state.printer.speed_changed = False
            state.point.update_from(self)
            state.point_systemXYZ.update_from(self_systemXYZ)
            return gcode_str.strip()  # strip the final space
