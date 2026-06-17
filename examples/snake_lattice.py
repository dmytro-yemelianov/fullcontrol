"""Snake-mode open lattice - a support-free open mesh tube, one continuous bead.

Inspired by FullControl's "Snake-Mode Soapdish": print one way, step up, print the other way, step
up, repeat. Each course goes once around the cylinder while its z zig-zags (a triangle wave, `bays`
peaks); the zig-zag is phase-shifted half a bay every course so a course's feet land on the previous
course's peaks - leaving open triangular holes between the diagonal struts. Alternate courses run in
opposite directions (the "snake"), so the whole open lattice is one seamless toolpath that prints
without support (each strut rests on the one below).
"""
from math import tau, sin, cos, floor

import fullcontrol as fc


def snake_lattice(radius: float = 20.0, height: float = 40.0, bays: int = 8,
                  course_height: float = 4.0, points_per_bay: int = 16,
                  extrusion_width: float = 0.6, extrusion_height: float = 0.3,
                  centre=(50.0, 50.0), first_layer_gap: float = 0.8) -> list:
    """Build a snake-mode open-lattice tube.

    radius: cylinder radius (mm); bays: triangular cells around the circumference;
    course_height: vertical rise per course = strut height (mm); points_per_bay: resolution.
    """
    cx, cy = centre
    courses = max(1, int(round(height / course_height)))
    per_course = bays * points_per_bay
    steps = [fc.ExtrusionGeometry(width=extrusion_width, height=extrusion_height)]
    for k in range(courses):
        z0 = first_layer_gap + k * course_height
        forward = (k % 2 == 0)
        for j in range(per_course + 1):
            f = j / per_course
            af = f if forward else 1.0 - f                 # snake: alternate courses reverse
            phi = af * tau
            phase = bays * af + 0.5 * (k % 2)              # half-bay offset on alternate courses
            tri = 1.0 - 2.0 * abs((phase - floor(phase)) - 0.5)   # triangle 0..1 (the zig-zag)
            steps.append(fc.Point(x=cx + radius * cos(phi), y=cy + radius * sin(phi),
                                  z=z0 + course_height * tri))
    return steps


if __name__ == '__main__':
    steps = snake_lattice()
    fc.transform(steps, 'gcode', fc.GcodeControls(
        printer_name='generic', save_as='snake_lattice',
        initialization_data={'nozzle_temp': 210, 'bed_temp': 40, 'primer': 'front_lines_then_y',
                             'extrusion_width': 0.6, 'extrusion_height': 0.3}))
    print('wrote snake_lattice.gcode')
