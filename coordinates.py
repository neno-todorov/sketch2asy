from typing import Tuple

import FreeCAD
import Part
import numpy


def get_vector_xy(vec: FreeCAD.Vector) -> Tuple[float, float]:
    return vec.x, vec.y


def get_point_xy(pnt: Part.Point) -> Tuple[float, float]:
    return pnt.X, pnt.Y


def get_array_xy(pnt: numpy.ndarray) -> Tuple[float, float]:
    return pnt[0], pnt[1]


def get_coordinates(pnt: FreeCAD.Vector | Part.Point) -> Tuple[float, float]:
    func_by_type = {
        FreeCAD.Vector: get_vector_xy,
        Part.Point: get_point_xy,
        numpy.ndarray: get_array_xy,
    }
    func = func_by_type.get(type(pnt))

    if func:
        return func(pnt)

    return 0, 0
