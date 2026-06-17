
from fullcontrol.visualize.state import State
from fullcontrol.visualize.plot_data import PlotData
from fullcontrol.visualize.controls import PlotControls
from fullcontrol.visualize.tips import tips
from fullcontrol.visualize.from_ir import visualize_from_ir
from fullcontrol.ir import resolve


def visualize(steps: list, plot_controls: PlotControls, show_tips: bool):
    '''
    Visualize the list of steps.

    The design is resolved to the shared Toolpath IR (user steps only, extruder defaulting on),
    then folded into PlotData paths.

    Parameters:
    - steps (list): The list of steps to visualize.
    - plot_controls (PlotControls, optional): The style of the plot can be adjusted by passing a PlotControls instance.

    Returns:
    - plot_data (PlotData): The plot data if `plot_controls.raw_data` is True, otherwise None.
    '''
    plot_controls.initialize()
    if show_tips: tips(plot_controls)

    state = State(steps, plot_controls)
    plot_data = PlotData(steps, state)
    toolpath = resolve(steps, plot_controls, include_procedures=False, initial_extruder_on=True)
    visualize_from_ir(toolpath, state, plot_data, plot_controls)

    if plot_controls.raw_data is True:
        return plot_data
    else:
        from fullcontrol.visualize.plotly import plot
        plot(plot_data, plot_controls)
