
import ast
import json
import operator
import os

SECONDS_PER_MINUTE = 60  # Cura speeds are mm/s; FullControl uses mm/min
from copy import deepcopy
from fullcontrol.gcode import Extruder, ManualGcode, Buildplate, Hotend, Fan
import fullcontrol.devices.community.singletool.base_settings as base_settings
from importlib import import_module, resources


# Restricted evaluator for start/end-gcode template terms (the values inside {}).
# Real templates only ever use numeric literals, simple arithmetic, calls to a few
# safe numeric builtins, and `data[...]` lookups. Anything else is rejected so that
# printer config / user overrides can never execute arbitrary code (previously eval()).
_ALLOWED_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_FUNCS = {'int': int, 'float': float, 'round': round,
                  'abs': abs, 'min': min, 'max': max}


def _eval_node(node, data):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, data)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_node(node.operand, data))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval_node(node.left, data), _eval_node(node.right, data))
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e, data) for e in node.elts)
    if isinstance(node, ast.Name):
        if node.id == 'data':
            return data
        raise ValueError(f"name {node.id!r} is not allowed in a gcode template expression")
    if isinstance(node, ast.Subscript):
        return _eval_node(node.value, data)[_eval_node(node.slice, data)]
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS and not node.keywords:
            return _ALLOWED_FUNCS[node.func.id](*[_eval_node(a, data) for a in node.args])
        raise ValueError("only int/float/round/abs/min/max calls are allowed in a gcode template expression")
    raise ValueError(f"unsupported gcode template expression: {ast.dump(node)}")


def safe_eval(expression: str, data: dict):
    '''Safely evaluate a single {} term from a start/end-gcode template.

    Supports numeric literals, +-*/ etc., the safe numeric builtins, and `data[...]`
    lookups. Raises ValueError for anything else (no arbitrary code execution).
    '''
    try:
        tree = ast.parse(expression.strip(), mode='eval')
    except SyntaxError as e:
        raise ValueError(f"invalid gcode template expression: {expression!r}") from e
    return _eval_node(tree, data)


from functools import cache


@cache
def load_json(library, file_name):
    # cached: the device library index (library.json) is read-only reference data, so the same
    # parsed dict can be reused across transforms instead of re-reading the file each time
    resource = resources.files('fullcontrol') / 'devices' / library / file_name
    with resource.open('r') as file:
        return json.load(file)

def find_terms_in_brackets(input_string):
    import re
    ' find all terms in the start_gcode string contained within {} and split the terms if they are comma separated'
    matches = re.findall(r'\{(.*?)\}', input_string)
    split_matches = [item.split(',') for item in matches]
    cleaned_matches = [[item.strip() for item in sublist]
                       for sublist in split_matches]
    cleaned_matches = [item for sublist in cleaned_matches for item in sublist]
    return set(cleaned_matches)


def replace_gcode_variables(printer_name: str, gcode_type: str, data: dict):
    # 'data' is used during the eval process to replace variables in the gcode string
    variables = find_terms_in_brackets(data[gcode_type])
    if len(variables) > 0:
        new_start_end_gcode = data[gcode_type]
        for variable in variables:
            new_start_end_gcode = new_start_end_gcode.replace('{' + variable + '}', str(safe_eval(variable, data)))
        data[gcode_type] = new_start_end_gcode


def import_printer(printer_name: str, user_overrides: dict):
    library_name = 'cura' if printer_name[:5] == 'Cura/' else 'community_minimal'
    printer_name = printer_name[5:] if library_name == 'cura' else printer_name[10:]
    library = load_json(library_name, os.path.join('library.json'))
    data = import_module(f'fullcontrol.devices.{library_name}.settings.{library[printer_name]}').default_initial_settings
    if library_name == 'cura':
        # Cura stores speeds in mm/s; FullControl works in mm/min
        data['print_speed'] = int(data['print_speed'] * SECONDS_PER_MINUTE)
        data['travel_speed'] = int(data['travel_speed'] * SECONDS_PER_MINUTE)
    data = {**base_settings.default_initial_settings, **data}
    data = {**data, **user_overrides}
    original_start_gcode = deepcopy(data['start_gcode'])
    replace_gcode_variables(printer_name, 'start_gcode', data)
    replace_gcode_variables(printer_name, 'end_gcode', data)
    
    starting_procedure_steps = []
    starting_procedure_steps.append(ManualGcode(text=data['start_gcode']))
    starting_procedure_steps.append(ManualGcode(
        text=f'; Time to print!!!!!\n; Printer name: {printer_name}\n; GCode created with FullControl - tell us what you\'re printing!\n; info@fullcontrol.xyz or tag FullControlXYZ on Twitter/Instagram/LinkedIn/Reddit/TikTok \n; New terms added to the hard-coded start_gcode ensure user-overrides are implemented:'))
    starting_procedure_steps.append(Extruder(relative_gcode=data["relative_e"]))
    if 'bed_temp' in user_overrides.keys() and 'bed_temp' not in original_start_gcode:
        starting_procedure_steps.append(Buildplate(temp=data["bed_temp"], wait=True))
    if 'nozzle_temp' in user_overrides.keys() and 'nozzle_temp' not in original_start_gcode:
        starting_procedure_steps.append(Hotend(temp=data["nozzle_temp"], wait=True))
    if 'fan_percent' in user_overrides.keys() and 'fan_percent' not in original_start_gcode:
        starting_procedure_steps.append(Fan(speed_percent=data["fan_percent"]))
    if 'print_speed_percent' in user_overrides.keys() and 'print_speed_percent' not in original_start_gcode:
        starting_procedure_steps.append(ManualGcode(text='M220 S' + str(data["print_speed_percent"])+' ; set speed factor override percentage'))
    if 'material_flow_percent' in user_overrides.keys() and 'material_flow_percent' not in original_start_gcode:
        starting_procedure_steps.append(ManualGcode(text='M221 S' + str(data["material_flow_percent"])+' ; set extrude factor override percentage'))
    data['starting_procedure_steps'] = starting_procedure_steps
    data['ending_procedure_steps'] = [ManualGcode(text=data['end_gcode'])]

    return data


def resolve_initialization_data(printer_name: str, user_overrides: dict) -> dict:
    '''Resolve a printer_name to its initialization data, dispatching across the
    printer sources: 'Cura/<name>' and 'Community/<name>' use the JSON+template
    importer; any other name is a singletool python profile. Raises a clear error
    for an unknown printer rather than a bare ModuleNotFoundError.'''
    if printer_name[:5] == 'Cura/' or printer_name[:10] == 'Community/':
        return import_printer(printer_name, user_overrides)
    module_name = f'fullcontrol.devices.community.singletool.{printer_name}'
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name == module_name:
            raise ValueError(
                f"unknown printer_name {printer_name!r}. Use a singletool profile name "
                f"(e.g. 'generic', 'ender_3', 'prusa_mk4'), or a 'Cura/<name>' / "
                f"'Community/<name>' name."
            ) from e
        raise  # a real import error inside the printer module - don't mask it
    return module.set_up(user_overrides)
