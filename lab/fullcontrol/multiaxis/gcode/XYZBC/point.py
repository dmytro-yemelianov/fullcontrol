from fullcontrol.common import Point as BasePoint
from fullcontrol.gcode.number_format import fmt
from copy import deepcopy
import numpy as np

class Point(BasePoint):
    'generic gcode Point with 5-axis aspects added/modified'
    b: float | None = None
    c: float | None = None

    def XYZBC_gcode(self, self_systemXYZ, p) -> str:
        'generate XYZBC gcode string to move from a point p to this point. return XYZBC string'
        s = ''
        if self_systemXYZ.x is not None and self_systemXYZ.x != p.x:
            s += f'X{fmt(round(self_systemXYZ.x, 6))} '
        if self_systemXYZ.y is not None and self_systemXYZ.y != p.y:
            s += f'Y{fmt(round(self_systemXYZ.y, 6))} '
        if self_systemXYZ.z is not None and self_systemXYZ.z != p.z:
            s += f'Z{fmt(round(self_systemXYZ.z, 6))} '
        if self_systemXYZ.b is not None and self_systemXYZ.b != p.b:
            s += f'B{fmt(round(self_systemXYZ.b, 6))} '
        if self_systemXYZ.c is not None and self_systemXYZ.c != p.c:
            s += f'C{fmt(round(self_systemXYZ.c, 6))} '
        return s if s != '' else None

    def inverse_kinematics(self, state):
        'calcualte system XYZ for the current point XYZ (in part coordinates)'

        def model2system(model_point, state, system_type: str):
            from math import cos, sin, tau
            system_point = deepcopy(model_point)
            if system_type == 'bc_bed':
                # 5-axis B-C bed inverse transform (LinuxCNC 5.3.2 inverse transformation):
                # https://linuxcnc.org/docs/html/motion/5-axis-kinematics.html
                inv_kin=np.zeros((3,3))
                inv_kin[0,:]= [cos(model_point.b*tau/360)*cos(model_point.c*tau/360), -sin(model_point.c*tau/360)*cos(model_point.b*tau/360), sin(model_point.b*tau/360)]
                inv_kin[1,:]= [sin(model_point.c*tau/360), cos(model_point.c*tau/360),0]
                inv_kin[2,:]= [-sin(model_point.b*tau/360)*cos(model_point.c*tau/360), sin(model_point.b*tau/360)*sin(model_point.c*tau/360), cos(model_point.b*tau/360)]

                # the model point is expressed relative to the rotation centre (bc_intercept),
                # so rotate it by the bed rotation R(B,C) and translate into the machine frame:
                #   system = R(B,C) @ model + bc_intercept
                inv_kin = np.matmul(inv_kin, np.array([model_point.x, model_point.y, model_point.z]))
                x_system = inv_kin[0] + state.printer.bc_intercept.x
                y_system = inv_kin[1] + state.printer.bc_intercept.y
                z_system = inv_kin[2] + state.printer.bc_intercept.z

            system_point.x = round(x_system, 6)
            system_point.y = round(y_system, 6)
            system_point.z = round(z_system, 6)
            return system_point

        # make sure undefined attributes of the current point (self) are taken from the point in state
        model_point = deepcopy(state.point)
        model_point.update_from(self)
        # inverse kinematics:
        system_point = model2system(model_point, state, 'bc_bed')
        return system_point
