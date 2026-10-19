from __future__ import annotations

from .base import SPaTProvider


class StubSPaTProvider(SPaTProvider):
    """Placeholder for the real SPaT feed. Returns no data for every signal.

    The router treats "no data" as "assume no wait", so with this provider it behaves like an
    ordinary shortest-time router. To go live, replace this with an adapter that implements
    `wait_s` against a real source (agency SPaT/ATSPM feed, vendor API, or timing inferred from
    floating car data).
    """

    name = "live"
    label = "Live SPaT feed (not connected)"
    is_simulated = False
    connected = False

    def wait_s(self, signal_id: int, phase_group: int, t_epoch: float) -> float | None:
        return None
