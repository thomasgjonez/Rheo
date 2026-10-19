from __future__ import annotations

from .base import SignalPlan, SPaTProvider, Window

_MASK = (1 << 64) - 1
CYCLES_S = (70, 80, 90, 100, 110, 120)
CLEARANCE_S = 5.0  # yellow + all-red between the two phases


def _mix64(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & _MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _MASK
    return x ^ (x >> 31)


def _unit(*parts: int) -> float:
    h = 0
    for p in parts:
        h = _mix64(h ^ (p & _MASK))
    return h / float(1 << 64)


def _window(start: float, length: float, cycle: float) -> tuple[Window, ...]:
    s = start % cycle
    e = s + length
    return ((s, e),) if e <= cycle else ((s, cycle), (0.0, e - cycle))


class SimulatedSPaTProvider(SPaTProvider):
    """Deterministic, made-up signal timing for every signalized intersection.

    Each signal gets a fixed cycle length, offset, and green split derived from a hash of its OSM
    id, then runs on real wall-clock time. Signals are independent (no corridor coordination),
    which is harsher than a well-coordinated arterial; savings measured against it are
    illustrative only, not a forecast of real-world performance.
    """

    name = "simulated"
    label = "Simulated signal timing"
    is_simulated = True
    connected = True

    def __init__(self, seed: int = 1):
        self.seed = seed
        self._plans: dict[int, SignalPlan] = {}

    def plan(self, signal_id: int) -> SignalPlan:
        plan = self._plans.get(signal_id)
        if plan is None:
            plan = self._build(signal_id)
            self._plans[signal_id] = plan
        return plan

    def _build(self, signal_id: int) -> SignalPlan:
        s = self.seed
        cycle = float(CYCLES_S[int(_unit(s, signal_id, 1) * len(CYCLES_S))])
        offset = _unit(s, signal_id, 2) * cycle
        usable = cycle - 2 * CLEARANCE_S
        green0 = usable * (0.4 + 0.2 * _unit(s, signal_id, 3))
        green1 = usable - green0
        start1 = offset + green0 + CLEARANCE_S
        return SignalPlan(
            cycle_s=cycle,
            green_windows=(_window(offset, green0, cycle), _window(start1, green1, cycle)),
        )

    def wait_s(self, signal_id: int, phase_group: int, t_epoch: float) -> float | None:
        return self.plan(signal_id).wait_s(phase_group, t_epoch)
