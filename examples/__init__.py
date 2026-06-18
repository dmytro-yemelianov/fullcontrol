"""Reimplemented FullControl demo designs, as clean parametric functions.

The classic fullcontrol.xyz / `models/` demos are written as flat notebook scripts. These are the
same designs reimplemented as importable, parametric, *self-contained* functions: each returns a
plain `list` of FullControl steps that already includes its own `ExtrusionGeometry`, so it can be
fed straight to any backend (`gcode` / `plot` / `simulation` / `validate`) without extra controls.

    import fullcontrol as fc
    from examples import spiral_vase
    steps = spiral_vase()
    gcode = fc.transform(steps, 'gcode', fc.GcodeControls(printer_name='generic',
                         initialization_data={'nozzle_temp': 210}))

Every design here is covered by tests/unit/test_examples.py (each one resolves to gcode, simulates,
and validates clean). See docs/gallery.md for the catalogue and the roadmap of designs to add next.
"""
from examples.spiral_vase import spiral_vase
from examples.ripple_vase import ripple_vase
from examples.nonplanar_spacer import nonplanar_spacer
from examples.wave_bowl import wave_bowl
from examples.gyroid_infill import gyroid_infill
from examples.twisted_polygon_vase import twisted_polygon_vase
from examples.helical_screw import helical_screw
from examples.surface_texture import revolve, textured_cone
from examples.mobius_band import mobius_band
from examples.trefoil_tube import trefoil_tube
from examples.optimization_demo import towers_grid, optimization_report
from examples.snake_soapdish import snake_soapdish
from examples.validation_gauntlet import validation_gauntlet

# GALLERY holds the printable designs (each name -> a function returning a step list). The
# validation_gauntlet (returns a dict of rule-tripping designs) and the print_time_study tool are
# different shapes, so they are exported on their own rather than registered here.
GALLERY = {
    'spiral_vase': spiral_vase,
    'ripple_vase': ripple_vase,
    'nonplanar_spacer': nonplanar_spacer,
    'wave_bowl': wave_bowl,
    'gyroid_infill': gyroid_infill,
    'twisted_polygon_vase': twisted_polygon_vase,
    'helical_screw': helical_screw,
    'textured_cone': textured_cone,
    'mobius_band': mobius_band,
    'trefoil_tube': trefoil_tube,
    'towers_grid': towers_grid,
    'snake_soapdish': snake_soapdish,
}

__all__ = ['spiral_vase', 'ripple_vase', 'nonplanar_spacer', 'wave_bowl', 'gyroid_infill',
           'twisted_polygon_vase', 'helical_screw', 'textured_cone', 'revolve', 'mobius_band',
           'trefoil_tube', 'towers_grid', 'snake_soapdish', 'optimization_report', 'validation_gauntlet', 'GALLERY']
