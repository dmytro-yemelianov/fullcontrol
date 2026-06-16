from fullcontrol.core.base import BaseModelPlus


class SimulationResult(BaseModelPlus):
    '''Summary metrics from simulating a design - a fast estimate (kinematics/accel are
    not modelled, so times are upper-ish estimates), useful for print-time/material
    estimates and spotting over-extrusion (peak flow).'''
    total_time_s: float = 0.0
    print_time_s: float = 0.0
    travel_time_s: float = 0.0
    extruding_distance: float = 0.0   # mm of extruding moves
    travel_distance: float = 0.0      # mm of travel moves
    extruded_volume: float = 0.0      # mm^3 of deposited material
    filament_length: float = 0.0      # mm of feedstock consumed
    segment_count: int = 0
    max_flow_rate: float = 0.0        # mm^3/s peak volumetric flow

    def summary(self) -> str:
        return (f'time ~{self.total_time_s:.1f}s (print {self.print_time_s:.1f}s, '
                f'travel {self.travel_time_s:.1f}s); filament {self.filament_length:.1f}mm '
                f'({self.extruded_volume:.1f}mm^3); {self.segment_count} segments; '
                f'peak flow {self.max_flow_rate:.2f}mm^3/s')
