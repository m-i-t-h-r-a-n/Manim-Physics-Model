# -*- coding: utf-8 -*-
""" 
TIMEBASE MODULE (SIMPLE WORDS + LONG EXPLANATIONS)
==================================================

What this file gives you
------------------------
1) A small **TimeWindow** data class: it remembers the smallest and largest time
   you want to allow (for example from 0 seconds to 2 seconds).
2) A **Timebase** class: this is the **brain** that controls model time.
   - You can play, pause, change speed, reverse, and jump (seek) to any time.
   - You can choose how time behaves at the ends of the window: stop there (clamp),
     loop back to the start (loop), or bounce back and forth (ping-pong).
   - You can attach **cues**, which are like simple keyframes for actions.
     *Instant cue*: do something exactly at one moment.
     *Range cue*: do something while time is inside a time interval.
   - It is careful to avoid missing important moments even if a frame is slow.

Why we need this
----------------
In physics animations, lots of things must happen at the **same time**.
We do not want every object to manage its own clock. Instead, we create one
shared clock (the *model time*) and let everything read from it. That way,
play/pause/speed/reverse/seek affect **all** objects in a clean and predictable way.

How it avoids skipping events
-----------------------------
Sometimes your computer draws a frame late. If we just moved time by a big chunk,
we could jump **over** a special moment (for example, an impact at 1.20 s). To make
this reliable, we use two ideas:
1) We **clamp** the amount of real time we accept per frame (for example, at most
   1/30 of a second per frame). If a frame arrives late, we take smaller internal
   steps so we do not jump too far at once.
2) When we check cues, we do not ask "is time exactly equal to 1.20?". Instead we
   look at the **segment** from the previous time to the new time. If the special
   moment lies anywhere inside that segment, we trigger the cue. This works in
   forward motion, in reverse, and during ping-pong.


Quick example (how to use in a Scene)
-------------------------------------
    from manim import *
    from timebase import Timebase, TimeWindow

    class Demo(Scene):
        def construct(self):
            time = Timebase(t0=0.0, rate=1.0, wrap="pingpong", window=TimeWindow(0.0, 2.0))
            self.add(time)  # add so the updater runs every frame

            dot = Dot(radius=0.1, color=BLUE)
            self.add(dot)

            def y_of_time(t):
                return 3.0 - 4.9*(t**2)   # a simple y(t) = y0 - 1/2 g t^2

            # Move the dot every frame based on the **shared** model time
            dot.add_updater(lambda m, dt: m.move_to([0, y_of_time(time.model_time()), 0]))

            # Flash exactly when t crosses 1.0 seconds
            time.on(1.0, lambda t: self.play(Flash(dot, time_width=0.3)))

            self.wait(6)

The full API is explained again right above each method.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Tuple, Literal
from manim import VGroup, Mobject, ValueTracker

# ----------------------------
# Basic types
# ----------------------------
WrapMode = Literal["clamp", "loop", "pingpong"]

@dataclass
class TimeWindow:
    '''
    TimeWindow purely provides a limiter/container for the time, that is,  a window for the model time.
    '''
    """A simple container for the valid time range.

    t_min: the smallest allowed time (left end of the window).
    t_max: the largest allowed time (right end of the window).

    If t_max is +infinity, only the **clamp** wrap mode makes sense, because
    looping and ping-pong need a finite length window.
    """
    t_min: float = 0.0
    t_max: float = float("inf")


# ----------------------------
# Timebase (the shared clock)
# ----------------------------
class Timebase(VGroup):
    """A scene-agnostic, shared clock for physics animations.

    The Timebase holds a single number called **model time**. On every frame,
    it advances this time according to the current playback **rate** and the
    chosen **wrap mode**. All your objects should *read* this time and update
    themselves accordingly.

    Key features in simple words:
    - Play / Pause / Toggle
    - Speed control (including reverse)
    - Seek (jump) to any time
    - Wrap modes inside a time window: clamp, loop, ping-pong
    - Cue system (do something at a moment, or while inside a range)
    - "Don’t skip events" safety: clamp the per-frame step and do crossing checks
    """

    def __init__(
        self,
        t0: float = 0.0,                 # where model time starts
        rate: float = 1.0,               # model seconds per real second (can be negative, decimal, and anything in between)
        wrap: WrapMode = "clamp",        # how to behave at the window ends (clamp: clamp the time to the window, loop: loop the time (tmax -> t0), pingpong: bounce back and forth)
        window: TimeWindow = TimeWindow(0.0, float("inf")),
        clamp_dt: float = 1/30,          # cap per-frame real dt (helps reliability)
    ) -> None:
        super().__init__()

        self._time: ValueTracker = ValueTracker(t0)     # the current model time
        self._prev_time: float = t0                      # previous frame's model time
        self._rate: ValueTracker = ValueTracker(rate)    # playback speed
        self._running: ValueTracker = ValueTracker(1.0)  # 1.0 = playing, 0.0 = paused

        self.wrap_mode: WrapMode = wrap
        self.window: TimeWindow = window
        self.clamp_dt: float = clamp_dt

        self._dir_sign: float = 1.0

        self._instant_cues: List[Tuple[float, Callable[[float], None]]] = []
        self._range_cues: List[Tuple[float, float, Callable[[float], None], Callable[[float], None]]] = []
        self._range_state: dict[Tuple[float, float, int], bool] = {}

        self.add_updater(self._step)

    """
    Time Functions
    ==============

    The following functions make the described changes to the time. 
    They play different roles, as explained below.
    
    """

    # -----------------------
    # Public Time Getters
    # -----------------------


    def model_time(self) -> float:
        # Return the current model time as a float value.
        return self._time.get_value()

    def rate(self) -> float:
        # Return the current playback rate/speed as a float value (model seconds per real second)
        return self._rate.get_value()

    def running(self) -> bool:
        # Returns the running state: 1.0 for playing, 0.0 for paused (as mentioned in the self._running() line)
        return bool(round(self._running.get_value()))

    def play(self) -> None:
        # sets the value of running to 1.0, i.e. the state of running to "True" or "Playing"
        self._running.set_value(1.0)

    def pause(self) -> None:
        # sets the value of running to 0.0, i.e. the state of running to "False" or "Paused"
        self._running.set_value(0.0)

    def toggle(self) -> None:
        # toggles the (self._running) running state: if running is playing, set it to paused, and vice versa.
        self._running.set_value(0.0 if self.running() else 1.0)

    def set_rate(self, r: float) -> None:
        # sets the value of rate/speed to a specific float value (e.g 0.5x makes the video half as fast)
        self._rate.set_value(r)

    def speed(self, s: float) -> None:
        # another way to set the rate/speed. 
        self.set_rate(s)

    def reverse(self) -> None:
        # forcibly makes the video play backwards (by taking the negative of absolute value of the rate)
        self._rate.set_value(-abs(self.rate()))

    def forward(self) -> None:
        # forcibly makes the video play forward (by taking the absolute value of the rate)
        self._rate.set_value(abs(self.rate()))

    def seek(self, t: float) -> None:
        # jumps the model time to a specific time. It uses the _wrap function to ensure the time is within the window.
        self._time.set_value(self._wrap(t))
        self._prev_time = self._time.get_value()

    def set_window(self, t_min: float, t_max: float) -> None:
        # sets the time window of the timebase to a specifc range denoted by (t_min, t_max)
        self.window = TimeWindow(t_min, t_max)
        self.seek(self._time.get_value())

    def set_wrap(self, mode: WrapMode) -> None:
        # sets the wrap mode of the timebase to a specific mode out of clamp, loop, and pingpong
        self.wrap_mode = mode
        self.seek(self._time.get_value())

    # -----------------------
    # Cue Management Functions
    # -----------------------

    """
    What is a Cue?
    ====================

    In a physics model/animation, many animations can happen at the same time.
    A cue essentially gives the instructions of a function/actions, "fn", that has to happen at a specific time "t".
    """

    def on(self, t: float, fn: Callable[[float], None]) -> None:
        
        self._instant_cues.append((t, fn))

    def on_range(
        self,
        t0: float,
        t1: float,
        on_enter: Callable[[float], None],
        on_exit: Callable[[float], None] = lambda _: None,
    ) -> None:
        key = (t0, t1, len(self._range_cues))
        self._range_cues.append((t0, t1, on_enter, on_exit))
        self._range_state[key] = False

    def clear_cues(self) -> None:
        self._instant_cues.clear()
        self._range_cues.clear()
        self._range_state.clear()

    def _step(self, mob: Mobject, dt_real: float) -> None:
        if not self.running():
            return

        dt = dt_real if dt_real <= self.clamp_dt else self.clamp_dt

        eff_rate = self.rate() * (self._dir_sign if self.wrap_mode == "pingpong" else 1.0)

        old = self._time.get_value()
        proposed = old + eff_rate * dt

        new, bounced = self._wrap_with_bounce(old, proposed)

        if bounced and self.wrap_mode == "pingpong":
            self._dir_sign *= -1.0

        self._prev_time = old
        self._time.set_value(new)

        self._fire_cues()

    def _wrap(self, t: float) -> float:
        a, b = self.window.t_min, self.window.t_max

        finite = (a < b) and (b != float("inf"))
        if self.wrap_mode == "clamp" or not finite:
            return max(a, min(t, b))

        length = b - a
        if length == 0:
            return a

        if self.wrap_mode == "loop":
            return a + ((t - a) % length)

        if self.wrap_mode == "pingpong":
            m = (t - a) % (2 * length)
            return a + (m if m <= length else 2 * length - m)

        return t

    def _wrap_with_bounce(self, t_before: float, t_after: float) -> Tuple[float, bool]:
        a, b = self.window.t_min, self.window.t_max

        finite = (a < b) and (b != float("inf"))
        if self.wrap_mode == "clamp" or not finite:
            return (max(a, min(t_after, b)), False)

        if self.wrap_mode == "loop":
            return (self._wrap(t_after), False)

        wrapped = self._wrap(t_after)
        eps = 1e-9
        hit_left  = (t_before - a) * (t_after - a) < 0 or abs(wrapped - a) < eps
        hit_right = (t_before - b) * (t_after - b) < 0 or abs(wrapped - b) < eps
        return (wrapped, hit_left or hit_right)

    def _fire_cues(self) -> None:
        t_prev = self._prev_time
        t_now = self._time.get_value()

        def between(x: float, u: float, v: float) -> bool:
            lo, hi = (u, v) if u <= v else (v, u)
            return lo <= x <= hi

        if t_prev != t_now:
            for tc, fn in self._instant_cues:
                if between(tc, t_prev, t_now):
                    fn(tc)

        for idx, (t0, t1, on_enter, on_exit) in enumerate(self._range_cues):
            key = (t0, t1, idx)
            inside_now = between(t_now, t0, t1)
            was_inside = self._range_state.get(key, False)

            if inside_now and not was_inside:
                on_enter(t_now)
                self._range_state[key] = True
            elif not inside_now and was_inside:
                on_exit(t_now)
                self._range_state[key] = False
