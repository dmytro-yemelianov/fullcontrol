from pydantic import BaseModel
from fullcontrol.common import Point


class PlotAnnotation(BaseModel):
    '''
    Represents an annotation for a plot.

    Attributes:
        point (Optional[Point]): The xyz point associated with the annotation. If not defined, the previous point in the list of steps before this annotation was defined is used.
        label (Optional[str]): The label text to be shown on the plot.

    Methods:
        visualize(state: 'State', plot_data: 'PlotData', plot_controls: PlotControls) -> None:
            Process a PlotAnnotation in a list of steps supplied by the designer to update plot_data and state.
    '''
    point: Point | None = None
    label: str | None = None
