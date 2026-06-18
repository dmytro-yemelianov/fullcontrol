"""Module entry point: ``python -m fullcontrol.gcode_engine verify|optimise|inspect …``."""
import sys

from fullcontrol.gcode_engine.cli import main

if __name__ == '__main__':
    sys.exit(main())
