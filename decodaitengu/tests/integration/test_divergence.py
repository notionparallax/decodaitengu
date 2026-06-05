"""Integration tests: validate plan_dive() against Subsurface reference data.

These tests ensure our output stays within documented tolerance bands.
If a test fails, it means the model has drifted from its expected behaviour.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from decodaitengu import Gas, plan_dive
from decodaitengu.types import DiveSummary

REFERENCE_FILE = Path(__file__).parent / "reference_data.json"

with REFERENCE_FILE.open() as f:
    REFERENCE = json.load(f)

# Maximum acceptable per-stop divergence from our own regression values (minutes).
# This is NOT the divergence from Subsurface â€” it's a regression guard.
REGRESSION_TOLERANCE = 1  # min

# Maximum acceptable per-stop divergence from Subsurface (minutes).
# Exceeding this means the model has moved further from the reference planner.
SUBSURFACE_TOLERANCE = 5  # min per stop


def _run_plan(plan: dict[str, Any]) -> DiveSummary:
    deco_gases = [
        Gas(o2=g["o2"], he=g["he"], switch_depth=g["switch_depth_m"]) for g in plan["deco_gases"]
    ]
    meta_gf = tuple(REFERENCE["_meta"]["gf"])
    gf = tuple(plan["gf"]) if "gf" in plan else meta_gf
    descent_rate = plan.get("descent_rate_m_per_min", REFERENCE["_meta"]["descent_rate_m_per_min"])
    raw_ar = plan.get("ascent_rate", REFERENCE["_meta"]["ascent_rate_m_per_min"])
    ascent_rate = [tuple(seg) for seg in raw_ar] if isinstance(raw_ar, list) else raw_ar
    return plan_dive(
        depth=plan["depth_m"],
        bottom_time=plan["bottom_time_min"],
        back_gas=Gas(o2=plan["back_gas"]["o2"], he=plan["back_gas"]["he"]),
        deco_gases=deco_gases if deco_gases else None,
        gf=gf,
        descent_rate=float(descent_rate),
        ascent_rate=ascent_rate,
    )


@pytest.mark.parametrize(
    "plan",
    REFERENCE["plans"],
    ids=[p["id"] for p in REFERENCE["plans"]],
)
class TestRegressionBounds:
    """Fail if our output drifts from its documented values."""

    def test_stops_within_regression_tolerance(self, plan):
        result = _run_plan(plan)
        actual = {s.depth: s.time for s in result.stops}
        for depth_str, exp_time in plan["our_stops"].items():
            depth = float(depth_str)
            actual_time = actual.get(depth, 0)
            assert abs(actual_time - exp_time) <= REGRESSION_TOLERANCE, (
                f"{plan['id']}: stop at {depth}m drifted to {actual_time} min "
                f"(expected {exp_time} Â±{REGRESSION_TOLERANCE})"
            )


@pytest.mark.parametrize(
    "plan",
    REFERENCE["plans"],
    ids=[p["id"] for p in REFERENCE["plans"]],
)
class TestSubsurfaceDivergenceBounds:
    """Fail if divergence from Subsurface exceeds documented tolerance."""

    def test_per_stop_within_subsurface_tolerance(self, plan):
        result = _run_plan(plan)
        actual = {s.depth: s.time for s in result.stops}
        all_depths = set(float(d) for d in plan["subsurface_stops"]) | set(actual)
        for depth in all_depths:
            our_time = actual.get(depth, 0)
            sub_time = plan["subsurface_stops"].get(str(int(depth)), 0)
            assert abs(our_time - sub_time) <= SUBSURFACE_TOLERANCE, (
                f"{plan['id']}: stop at {depth}m diverges by "
                f"{our_time - sub_time} min from Subsurface (tolerance Â±{SUBSURFACE_TOLERANCE})"
            )
