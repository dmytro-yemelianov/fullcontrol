from pydantic import BaseModel


class GcodeComment(BaseModel):
    '''
    Represents a comment in a line of Gcode.

    Attributes:
        text (Optional[str]): The comment to be added as a new line of Gcode.
        end_of_previous_line_text (Optional[str]): The comment to be added at the end of the previous line of Gcode.
    '''

    text: str | None = None
    end_of_previous_line_text: str | None = None
