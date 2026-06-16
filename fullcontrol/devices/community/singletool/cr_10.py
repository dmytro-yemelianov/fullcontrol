from fullcontrol.gcode import ManualGcode
import fullcontrol.devices.community.singletool.ender_3 as ender_3
from fullcontrol.devices.community.singletool._procedure import replace_step, manual_gcode_startswith


def set_up(user_overrides: dict):
    ''' DO THIS
    '''

    # copy the ender_3 initialization data except change the build-volume header line
    initialization_data = ender_3.set_up(user_overrides)
    replace_step(initialization_data['starting_procedure_steps'],
                 manual_gcode_startswith(';MAXX'),
                 ManualGcode(text=';MAXX:300\n;MAXY:300\n;MAXZ:400\n'),
                 description='MAXX build-volume header')

    return initialization_data
