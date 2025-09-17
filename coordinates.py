from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Tuple
import numpy as np

from manim import *

@dataclass
class Coords:

    '''
    METERS PER UNIT
    =================
    A scene in manim is comprised of a 14 x 8 (l x b) grid.
    Setting meters_per_unit to 1.0 means that 1 meter in the scene is equal to 1 unit in the scene.
    Setting meters_per_unit to 2.0 means that 1 meter in the scene is equal to 2 units in the scene, and so on.

    ORIGIN OF THE SCENE
    ====================
    This simple sets the origin of the world with respect to the scene. If the origin_scene is set to (0.0, 0.0), then the origin of 
    the world coincides with the origin of the scene. If the origin_scene is set to (1.0, 1.0), then the origin of the world is 1 unit 
    to the right and 1 unit up from the origin of the scene.
    '''

    meters_per_unit: float = 1.0
    origin_scene: Tuple[float, float] = (0.0, 0.0)

    '''
    ORIENTATION OF THE SCENE
    =========================
    x_right determines if the +X axis, that is the right direction X axis is positive, or negative
    y_up determines if the +Y axis, that is the up direction Y axis is positive, or negative
    '''

    x_right: int = 1 
    y_up: int = 1

    def __post_init__(self):
        # Basic validation so mistakes fail fast and clearly
        if self.meters_per_unit == 0:
            raise ValueError("meters_per_unit cannot be zero")
        if self.x_right not in (-1, 1):
            raise ValueError("x_right must be +1 or -1")
        if self.y_up not in (-1, 1):
            raise ValueError("y_up must be +1 or -1")

    # -------------------
    # LENGTH CONVERSIONS
    # -------------------

    def world_len_to_scene(self, meters: float) -> float:
        # this is supposed to convert a world length in meter to scene scene units
        if self.meters_per_unit == 0:
            raise ValueError("The meters_per_unit conversion cannot be zero.")
        return meters / self.meters_per_unit

    '''
    Example usage:

    - Say I want to make a circle that is 1 meter in radius in the scene. However, I don't know what 1 meter translates to in the scene. 
    - In such a case, I would use the world_len_to_scene method to convert the 1 meter to scene units.

    Code:

    coords = Coords(meters_per_unit = 1.0)
    circle_world_radius = 1.0 --> this means that the circle is 1 meter in radius in the real world.
    circle_scene_radius = coords.world_len_to_scene(circle_world_radius) --> this means that the circle is circle_scene_radius units in radius in the scene.

    '''

    def scene_len_to_world(self, scene_units: float) -> float:
        # this is supposed to convert a scene length in units to world length in meters
        return scene_units * self.meters_per_unit
    
    '''
    Example usage:

    - Say I want to make a circle that is 10 units in radius in the scene. However, I don't know what 10 units translates to in the real world. 
    - In such a case, I would use the scene_len_to_world method to convert the 10 units to world length in meters.

    Code:

    coords = Coords(meters_per_unit = 1.0)
    circle_scene_radius = 10.0 --> this means that the circle is 10 units in radius in the scene.
    circle_world_radius = coords.scene_len_to_world(circle_scene_radius) --> this means that the circle is circle_world_radius meters in radius in the real world.

    '''
    # -------------------
    # POINT CONVERSIONS
    # -------------------

    def world_to_scene_point(self, x_m: float, y_m: float) -> np.ndarray:
        # this is supposed to convert World (x, y) coordinates (which are in meters) --> scene's [x, y, 0] coords
        sc_x = self.origin_scene[0] + self.x_right * self.world_len_to_scene(x_m)
        sc_y = self.origin_scene[1] + self.y_up * self.world_len_to_scene(y_m)
        return np.array([sc_x, sc_y, 0.0])

    def scene_to_world_point(self, x_sc: float, y_sc: float) -> np.ndarray:
        # this converts scene (x_sc, y_sc) -> world (x_m, y_m)
        
        dx_scene = (x_sc - self.origin_scene[0]) * self.x_right # subtract the x distance from origin first, then apply axis direction, then convert units
        dy_scene = (y_sc - self.origin_scene[1]) * self.y_up # subtract the y distance from origin first, then apply axis direction, then convert units

        '''
        ORIGIN SUBTRACTION
        ==================
        - This was because, if the world origin was shifted in the scene, i.e. not at (0, 0), world_x and world_y would be shifted in the scene by the same amount 
        as the origin_scene's x and y values are shifted

        '''

        world_x = self.scene_len_to_world(dx_scene)
        world_y = self.scene_len_to_world(dy_scene)
        return np.array([world_x, world_y])


def bind_world_position(mobj: Mobject, world_pos_fn: Callable[[float], Tuple[float, float]], time, coords: 'Coords') -> None:

    def _upd(_m: Mobject, _dt: float):
        t = time.model_time()
        x_m, y_m = world_pos_fn(t)
        _m.move_to(coords.world_to_scene_point(x_m, y_m))
    mobj.add_updater(_upd)

