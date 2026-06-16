from pydantic import BaseModel


class ModelControls(BaseModel):
    ''' Controls to adjust the style of a generated 3D model. '''
    stl_filename: str | None = '3d_model'
    include_date: bool | None = True
    tube_shape: str | None = 'rectangle'  # 'rectangle'/'diamond'/'hexagon'/'octagon'
    tube_type: str | None = 'flow'  # 'flow'/'cylinders'
    stl_type: str | None = 'ascii'  # 'binary'/'ascii'
    stls_combined: bool | None = True
    # initialization_data is information about initial printing conditions, which may be
    #  changed by the fullcontrol 'design', whereas the above attributes are never changed
    #  by the 'design'.
    # Values passed for initialization_data overwrite the default initialization data of
    #  the printer.
    initialization_data: dict | None = {}

    def shape_properties(self):
        return {
            'rectangle': (4,   0, True),
            'diamond':   (4,   1, False),
            'hexagon':   (6, 0.4, False),
            'octagon':   (8, 0.4, True),
        }[self.tube_shape]
