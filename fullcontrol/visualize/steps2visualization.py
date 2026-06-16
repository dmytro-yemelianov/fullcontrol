
from fullcontrol.visualize.state import State
from fullcontrol.visualize.plot_data import PlotData
from fullcontrol.visualize.controls import PlotControls
from fullcontrol.visualize.tips import tips
from fullcontrol.visualize.renderers import render_visualize


def visualize(steps: list, plot_controls: PlotControls, show_tips: bool):
    '''
    Visualize the list of steps.

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
    for i, step in enumerate(steps):
        try:
            render_visualize(step, state, plot_data, plot_controls)
        except Exception as e:
            raise type(e)(f'error visualizing step {i} ({type(step).__name__}): {e}') from e
    plot_data.cleanup()

    if plot_controls.raw_data is True:
        return plot_data
    else:
        from fullcontrol.visualize.plotly import plot
        plot(plot_data, plot_controls)
