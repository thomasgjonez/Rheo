"""SPaT (Signal Phase and Timing) provider interface.

The router only ever talks to `SPaTProvider`. Real signal data - an agency/vendor
feed, or timing inferred from floating car data - plugs in by implementing `wait_s`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

Window = tuple[float, float]


@dataclass(frozen=True)
class SignalPlan:
    """Repeating green windows for the two approach groups at one intersection.

    Windows are [start, end) offsets in seconds within a cycle, anchored to the Unix epoch.
    This models pretimed signals; actuated signals need a plan refreshed from live data.
    """

    cycle_s: float
    green_windows: tuple[tuple[Window, ...], tuple[Window, ...]]

    def wait_s(self, group: int, t_epoch: float) -> float:
        phase = t_epoch % self.cycle_s
        soonest = None
        for start, end in self.green_windows[group]:
            if start <= phase < end:
                return 0.0
            gap = (start - phase) % self.cycle_s
            soonest = gap if soonest is None else min(soonest, gap)
        return soonest or 0.0


class SPaTProvider(ABC):
    name: str = "provider"
    label: str = "SPaT provider"
    is_simulated: bool = False
    connected: bool = True

    @abstractmethod
    def wait_s(self, signal_id: int, phase_group: int, t_epoch: float) -> float | None:
        """Seconds a vehicle arriving at `t_epoch` waits for green, or None if there is no data.

        `signal_id` is the OSM node id of the signalized intersection; `phase_group` is
        0 (roughly north/south approach) or 1 (roughly east/west).
        """
