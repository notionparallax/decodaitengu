"""Property-based tests for plan_dive using hypothesis.

These tests verify fundamental invariants that must hold across all valid inputs.
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from decodaitengu import Gas, plan_dive

# --- Strategies ---

reasonable_depth = st.floats(min_value=5.0, max_value=100.0)
reasonable_bottom_time = st.floats(min_value=5.0, max_value=120.0)
gf_low = st.floats(min_value=10.0, max_value=100.0)
gf_high = st.floats(min_value=10.0, max_value=100.0)
reasonable_o2 = st.integers(min_value=18, max_value=100)
reasonable_he = st.integers(min_value=0, max_value=60)


@st.composite
def valid_gas(draw: st.DrawFn) -> Gas:
    """Generate a valid gas mix where o2 + he <= 100."""
    o2 = draw(st.integers(min_value=18, max_value=100))
    he = draw(st.integers(min_value=0, max_value=min(60, 100 - o2)))
    return Gas(o2=o2, he=he)


@st.composite
def valid_gf(draw: st.DrawFn) -> tuple[float, float]:
    """Generate a valid GF pair where low <= high."""
    low = draw(st.floats(min_value=10.0, max_value=100.0))
    high = draw(st.floats(min_value=low, max_value=100.0))
    return (low, high)


# --- Property Tests ---


class TestMonotonicity:
    """Properties about monotonic relationships in dive planning."""

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_lower_gf_high_means_more_deco(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """Lower GF high (more conservative surfacing) should produce >= deco time."""
        assume(gf[1] > 20)  # Need room to make it more conservative
        assume(bottom_time > depth / 20.0 + 1)
        liberal = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        conservative_gf = (gf[0], gf[1] - 10)
        assume(conservative_gf[0] <= conservative_gf[1])  # GF_low must be <= GF_high
        conservative = plan_dive(depth=depth, bottom_time=bottom_time, gf=conservative_gf)
        assert conservative.total_deco_time >= liberal.total_deco_time - 0.01, (
            f"Conservative GF {conservative_gf} produced less deco "
            f"({conservative.total_deco_time}) than liberal {gf} ({liberal.total_deco_time})"
        )

    @given(
        depth=st.floats(min_value=10.0, max_value=60.0),
        bt1=st.floats(min_value=5.0, max_value=30.0),
        extra=st.floats(min_value=1.0, max_value=30.0),
    )
    @settings(max_examples=50, deadline=5000)
    def test_longer_bottom_time_means_more_deco(
        self, depth: float, bt1: float, extra: float
    ) -> None:
        """Longer bottom time should produce >= deco time."""
        bt2 = bt1 + extra
        assume(bt1 > depth / 20.0 + 1)
        r1 = plan_dive(depth=depth, bottom_time=bt1, gf=(30, 85))
        r2 = plan_dive(depth=depth, bottom_time=bt2, gf=(30, 85))
        assert r2.total_deco_time >= r1.total_deco_time - 0.01, (
            f"Longer dive ({bt2} min) has less deco ({r2.total_deco_time}) "
            f"than shorter ({bt1} min, {r1.total_deco_time})"
        )

    @given(
        d1=st.floats(min_value=10.0, max_value=40.0),
        extra_depth=st.floats(min_value=5.0, max_value=30.0),
        bottom_time=st.floats(min_value=15.0, max_value=40.0),
    )
    @settings(max_examples=50, deadline=5000)
    def test_deeper_dive_means_more_deco(
        self, d1: float, extra_depth: float, bottom_time: float
    ) -> None:
        """Deeper dive should produce >= deco time."""
        d2 = d1 + extra_depth
        assume(bottom_time > d2 / 20.0 + 1)
        r1 = plan_dive(depth=d1, bottom_time=bottom_time, gf=(30, 85))
        r2 = plan_dive(depth=d2, bottom_time=bottom_time, gf=(30, 85))
        assert r2.total_deco_time >= r1.total_deco_time - 0.01, (
            f"Deeper dive ({d2}m) has less deco ({r2.total_deco_time}) "
            f"than shallower ({d1}m, {r1.total_deco_time})"
        )


class TestTissueLoading:
    """Properties about tissue loading behaviour."""

    @given(
        depth=st.floats(min_value=15.0, max_value=80.0),
        bottom_time=st.floats(min_value=10.0, max_value=60.0),
    )
    @settings(max_examples=50, deadline=5000)
    def test_tissue_loading_above_surface_equilibrium(
        self, depth: float, bottom_time: float
    ) -> None:
        """After any non-trivial dive, tissues should be more loaded than surface equilibrium."""
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=(100, 100))
        # Surface equilibrium N2: 0.7902 * (1.01325 - 0.0627) ≈ 0.751 per compartment
        surface_n2_total = 0.7902 * (1.01325 - 0.0627) * 16
        actual_total = sum(result.tissues_final.n2_pressures)
        assert actual_total > surface_n2_total, (
            f"Total N2 tissue loading ({actual_total:.4f}) should exceed "
            f"surface equilibrium ({surface_n2_total:.4f}) after {depth}m/{bottom_time}min"
        )


class TestSurfacing:
    """Properties about valid dive completion."""

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_runtime_always_positive(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """Runtime must always be positive."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        assert result.runtime > 0

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_runtime_at_least_bottom_time(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """Runtime must be at least bottom time (includes ascent)."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        assert result.runtime >= bottom_time - 0.1

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_cns_non_negative(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """CNS must be non-negative."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        assert result.cns_percent >= 0.0

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_otu_non_negative(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """OTU must be non-negative."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        assert result.otu >= 0.0

    @given(
        depth=st.floats(min_value=5.0, max_value=30.0),
        bottom_time=st.floats(min_value=5.0, max_value=20.0),
    )
    @settings(max_examples=50, deadline=5000)
    def test_ndl_dive_has_no_stops(self, depth: float, bottom_time: float) -> None:
        """GF 100/100 on shallow/short dives should produce no stops."""
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=(100, 100))
        if result.ndl is not None:
            assert result.stops == []
            assert result.total_deco_time == 0.0

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_stops_at_3m_multiples(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """All deco stops must be at multiples of 3m."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        for stop in result.stops:
            assert stop.depth % 3.0 == pytest.approx(0.0, abs=0.01), (
                f"Stop at {stop.depth}m is not a multiple of 3"
            )

    @given(
        depth=reasonable_depth,
        bottom_time=reasonable_bottom_time,
        gf=valid_gf(),
    )
    @settings(max_examples=50, deadline=5000)
    def test_max_depth_matches_requested(
        self, depth: float, bottom_time: float, gf: tuple[float, float]
    ) -> None:
        """max_depth should equal the requested depth."""
        assume(bottom_time > depth / 20.0 + 1)
        result = plan_dive(depth=depth, bottom_time=bottom_time, gf=gf)
        assert result.max_depth == pytest.approx(depth)
