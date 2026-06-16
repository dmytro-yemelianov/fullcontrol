from pydantic import BaseModel
from fullcontrol import GcodeControls


class CodeControls(BaseModel):
    ''' Controls to adjust the language/format of a generated set of instructions (i.e. machine control code)'''
    code_format: str | None = None
    controls: GcodeControls | None = None
    filename: str | None = 'my_design'
