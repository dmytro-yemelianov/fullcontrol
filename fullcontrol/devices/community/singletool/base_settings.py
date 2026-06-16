default_initial_settings = {
    "print_speed": 1000,
    "travel_speed": 8000,
    "area_model": "rectangle",
    "extrusion_width": 0.4,
    "extrusion_height": 0.2,
    "nozzle_temp": 210,
    "bed_temp": 40,
    "chamber_temp": 0,  # enclosure/chamber temperature; overridden by e.g. voron_zero
    "tool_number": 0,
    "fan_percent": 100,
    "print_speed_percent": 100,
    "material_flow_percent": 100,
    "e_units": "mm",  # options: "mm" / "mm3"
    "relative_e": True,
    "manual_e_ratio": None,
    "dia_feed": 1.75,
    "retraction_distance": 1.0,  # default filament length retracted by fc.Retraction() (mm); tune per printer (bowden needs more)
    "retraction_speed": 2400,  # default retraction feedrate (mm/min = 40 mm/s)
    "travel_format": "G0",  # options: "G0" / "G1_E0"
    "gcode_flavor": "marlin",  # firmware dialect for command vocabulary (see gcode/flavor.py)
    "primer": "front_lines_then_y",
    "printer_command_list": {
        "home": "G28 ; home axes",
        "retract": "G10 ; retract",
        "unretract": "G11 ; unretract",
        "absolute_coords": "G90 ; absolute coordinates",
        "relative_coords": "G91 ; relative coordinates",
        "units_mm": "G21 ; set units to millimeters"
    }
}
