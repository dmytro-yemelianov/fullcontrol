from fullcontrol.gcode import ManualGcode
import fullcontrol.devices.community.singletool.toolchanger_T0 as toolchanger_T0
from fullcontrol.devices.community.singletool._procedure import replace_step, manual_gcode_text


def set_up(user_overrides: dict):
    ''' DO THIS
    '''

    # copy the toolchanger_T0 initialization data except select tool T1 instead of T0
    initialization_data = toolchanger_T0.set_up(user_overrides)
    replace_step(initialization_data['starting_procedure_steps'],
                 manual_gcode_text('T0'), ManualGcode(text='T1'), description='tool-select command')

    return initialization_data
