from fullcontrol.gcode import ManualGcode
import fullcontrol.devices.community.singletool.ender_3 as ender_3


def set_up(user_overrides: dict):
    '''Ender 5 Plus: identical to the Ender 3 procedure except for the build-volume
    (MAXX/MAXY/MAXZ) header, so delegate to ender_3 and patch that one step.'''
    initialization_data = ender_3.set_up(user_overrides)
    steps = initialization_data['starting_procedure_steps']
    for i, step in enumerate(steps):
        if getattr(step, 'text', None) and step.text.startswith(';MAXX'):
            steps[i] = ManualGcode(text=';MAXX:350\n;MAXY:350\n;MAXZ:400\n')
            break
    return initialization_data
