"""SPaT (Signal Phase and Timing) integration layer.

This module is the seam where a real signal data feed plugs in. Everything
downstream (routing.py) only talks to the `SPaTProvider` interface below —
swap `MockSPaTProvider` for a class that calls a live SPaT source (an
ATSPM/NTCIP export, a vendor API, a connected-vehicle SPaT broadcast) and
the routing engine needs no changes.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class SignalPlan:
    """The green schedule for one approach (one incoming edge) at one
    intersection, expressed as repeating offsets within a fixed cycle.

    green_windows: e.g. ((0, 25), (60, 70)) means green from t=0-25s and
    t=60-70s of every cycle_length_s period, anchored at reference_epoch_s.

    This models pretimed (fixed-cycle) signals exactly. Actuated/adaptive
    signals (which change their timing based on real-time demand) would
    need their plan re-fetched/re-predicted periodically rather than
    treated as a fixed schedule -- see `from_live_snapshot` below for the
    approximation used when only a single current-phase snapshot is available.
    """

    cycle_length_s: float
    green_windows: Tuple[Tuple[float, float], ...]
    reference_epoch_s: float = 0.0

    def wait_time_s(self, arrival_time_s: float) -> float:
        phase = (arrival_time_s - self.reference_epoch_s) % self.cycle_length_s
        for start, end in self.green_windows:
            if start <= phase < end:
                return 0.0
        if not self.green_windows:
            return 0.0
        upcoming = [(start - phase) % self.cycle_length_s for start, _ in self.green_windows]
        return min(upcoming)


class SPaTProvider:
    """Abstract source of signal timing. Implement `get_plan` against a real
    feed to make this a live system."""

    def get_plan(self, node_id: str, incoming_edge_id: str) -> Optional[SignalPlan]:
        raise NotImplementedError

    def wait_time_s(self, node_id: str, incoming_edge_id: Optional[str], arrival_time_s: float) -> float:
        if incoming_edge_id is None:
            return 0.0
        plan = self.get_plan(node_id, incoming_edge_id)
        if plan is None:
            return 0.0
        return plan.wait_time_s(arrival_time_s)


class MockSPaTProvider(SPaTProvider):
    """In-memory provider for the demo network. Stands in for a real feed."""

    def __init__(self) -> None:
        self._plans: Dict[Tuple[str, str], SignalPlan] = {}

    def set_plan(self, node_id: str, incoming_edge_id: str, plan: SignalPlan) -> None:
        self._plans[(node_id, incoming_edge_id)] = plan

    def get_plan(self, node_id: str, incoming_edge_id: str) -> Optional[SignalPlan]:
        return self._plans.get((node_id, incoming_edge_id))


def plan_from_live_snapshot(
    current_phase: str,
    seconds_to_change: float,
    green_duration_s: float,
    cycle_length_s: float,
    now_s: float,
) -> SignalPlan:
    """Build a SignalPlan from a single real-time SPaT reading.

    Real SPaT messages typically report "current phase" (red/yellow/green)
    plus a countdown to the next change, not the full cycle. This projects
    that one snapshot forward assuming fixed-time repetition -- a reasonable
    approximation for pretimed signals. For actuated signals this plan
    should be refreshed frequently (e.g. re-fetched per request) rather than
    trusted far into the future.
    """
    if current_phase == "green":
        green_start = now_s
    else:
        green_start = now_s + seconds_to_change

    start_offset = green_start % cycle_length_s
    end_offset = start_offset + green_duration_s

    if end_offset <= cycle_length_s:
        windows: Tuple[Tuple[float, float], ...] = ((start_offset, end_offset),)
    else:
        windows = ((start_offset, cycle_length_s), (0.0, end_offset - cycle_length_s))

    return SignalPlan(cycle_length_s=cycle_length_s, green_windows=windows)
