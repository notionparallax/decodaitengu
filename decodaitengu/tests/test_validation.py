#
# DecoTengu - dive decompression library.
#
# Tests for input validation (Issue #1: C1).
#


import pytest

from decodaitengu.planning import plan_dive
from decodaitengu.types import Cylinder, Gas


class TestGasValidation:
    """Test Gas dataclass input validation."""

    def test_valid_air(self):
        gas = Gas(o2=21, he=0)
        assert gas.n2 == 79

    def test_valid_trimix(self):
        gas = Gas(o2=21, he=35)
        assert gas.n2 == 44

    def test_valid_pure_o2(self):
        gas = Gas(o2=100, he=0)
        assert gas.n2 == 0

    def test_valid_heliox(self):
        gas = Gas(o2=21, he=79)
        assert gas.n2 == 0

    def test_o2_negative(self):
        with pytest.raises(ValueError, match="O2 must be between 0 and 100"):
            Gas(o2=-1, he=0)

    def test_o2_over_100(self):
        with pytest.raises(ValueError, match="O2 must be between 0 and 100"):
            Gas(o2=101, he=0)

    def test_he_negative(self):
        with pytest.raises(ValueError, match="He must be between 0 and 100"):
            Gas(o2=21, he=-5)

    def test_he_over_100(self):
        with pytest.raises(ValueError, match="He must be between 0 and 100"):
            Gas(o2=21, he=101)

    def test_o2_plus_he_over_100(self):
        with pytest.raises(ValueError, match="O2 \\+ He \\+ H2 must not exceed 100%"):
            Gas(o2=80, he=30)

    def test_o2_plus_he_exactly_100(self):
        """Edge case: O2 + He = 100% is valid (no N2)."""
        gas = Gas(o2=50, he=50)
        assert gas.n2 == 0.0

    def test_switch_depth_negative(self):
        with pytest.raises(ValueError, match="switch_depth must be >= 0"):
            Gas(o2=50, he=0, switch_depth=-1)

    def test_switch_depth_zero_ok(self):
        """switch_depth=0 is fine (back gas or no switch)."""
        gas = Gas(o2=21, he=0, switch_depth=0)
        assert gas.switch_depth == 0.0

    def test_o2_nan(self):
        with pytest.raises(ValueError, match="O2 must be between 0 and 100"):
            Gas(o2=float("nan"), he=0)

    def test_o2_inf(self):
        with pytest.raises(ValueError, match="O2 must be between 0 and 100"):
            Gas(o2=float("inf"), he=0)


class TestCylinderValidation:
    """Test Cylinder dataclass input validation."""

    def test_valid_cylinder(self):
        cyl = Cylinder(volume_litres=12.0, fill_bar=200)
        assert cyl.total_litres == 2400.0

    def test_volume_zero(self):
        with pytest.raises(ValueError, match="volume_litres must be positive"):
            Cylinder(volume_litres=0, fill_bar=200)

    def test_volume_negative(self):
        with pytest.raises(ValueError, match="volume_litres must be positive"):
            Cylinder(volume_litres=-1, fill_bar=200)

    def test_fill_zero(self):
        with pytest.raises(ValueError, match="fill_bar must be positive"):
            Cylinder(volume_litres=12, fill_bar=0)

    def test_fill_negative(self):
        with pytest.raises(ValueError, match="fill_bar must be positive"):
            Cylinder(volume_litres=12, fill_bar=-10)


class TestPlanDiveValidation:
    """Test plan_dive parameter validation."""

    # --- Depth ---
    def test_depth_zero(self):
        with pytest.raises(ValueError, match="depth must be a positive finite number"):
            plan_dive(depth=0, bottom_time=20)

    def test_depth_negative(self):
        with pytest.raises(ValueError, match="depth must be a positive finite number"):
            plan_dive(depth=-10, bottom_time=20)

    def test_depth_nan(self):
        with pytest.raises(ValueError, match="depth must be a positive finite number"):
            plan_dive(depth=float("nan"), bottom_time=20)

    def test_depth_inf(self):
        with pytest.raises(ValueError, match="depth must be a positive finite number"):
            plan_dive(depth=float("inf"), bottom_time=20)

    # --- Bottom time ---
    def test_bottom_time_zero(self):
        with pytest.raises(ValueError, match="bottom_time must be a positive finite number"):
            plan_dive(depth=30, bottom_time=0)

    def test_bottom_time_negative(self):
        with pytest.raises(ValueError, match="bottom_time must be a positive finite number"):
            plan_dive(depth=30, bottom_time=-5)

    # --- Rates ---
    def test_descent_rate_zero(self):
        with pytest.raises(ValueError, match="descent_rate must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, descent_rate=0)

    def test_descent_rate_negative(self):
        with pytest.raises(ValueError, match="descent_rate must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, descent_rate=-10)

    def test_ascent_rate_zero(self):
        with pytest.raises(ValueError, match="ascent_rate must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, ascent_rate=0)

    def test_ascent_rate_negative(self):
        with pytest.raises(ValueError, match="ascent_rate must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, ascent_rate=-10)

    def test_ascent_rate_profile_list_valid(self):
        result = plan_dive(
            depth=30,
            bottom_time=20,
            ascent_rate=[(6, 10), (0, 3)],
        )
        assert result.runtime > 0

    def test_ascent_rate_profile_dict_valid(self):
        result = plan_dive(
            depth=30,
            bottom_time=20,
            ascent_rate={6: 10, 0: 3},
        )
        assert result.runtime > 0

    def test_ascent_rate_profile_requires_surface_segment(self):
        with pytest.raises(ValueError, match="must include a surface segment"):
            plan_dive(depth=30, bottom_time=20, ascent_rate=[(6, 10)])

    def test_ascent_rate_profile_invalid_segment_rate(self):
        with pytest.raises(ValueError, match="segment 1 rate must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, ascent_rate=[(6, 10), (0, 0)])

    # --- GF ---
    def test_gf_low_zero(self):
        with pytest.raises(ValueError, match="gf_low must be in"):
            plan_dive(depth=30, bottom_time=20, gf=(0, 85))

    def test_gf_low_over_100(self):
        with pytest.raises(ValueError, match="gf_low must be in"):
            plan_dive(depth=30, bottom_time=20, gf=(101, 85))

    def test_gf_high_zero(self):
        with pytest.raises(ValueError, match="gf_high must be in"):
            plan_dive(depth=30, bottom_time=20, gf=(30, 0))

    def test_gf_high_over_100(self):
        with pytest.raises(ValueError, match="gf_high must be in"):
            plan_dive(depth=30, bottom_time=20, gf=(30, 200))

    def test_gf_low_greater_than_high(self):
        with pytest.raises(ValueError, match="gf_low must be <= gf_high"):
            plan_dive(depth=30, bottom_time=20, gf=(85, 30))

    def test_gf_low_equals_high_valid(self):
        """GF low == high is valid (e.g. GF 100/100 for no GF)."""
        result = plan_dive(depth=20, bottom_time=15, gf=(100, 100))
        assert result.runtime > 0

    def test_gf_1_percent_valid(self):
        """GF low of 1% should be accepted (not misinterpreted as 100%)."""
        result = plan_dive(depth=40, bottom_time=25, gf=(1, 85))
        # With GF low of 1%, first stop should be very deep
        assert result.total_deco_time > 0

    # --- SAC rates ---
    def test_sac_bottom_zero(self):
        with pytest.raises(ValueError, match="sac_bottom must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, sac_bottom=0)

    def test_sac_deco_negative(self):
        with pytest.raises(ValueError, match="sac_deco must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, sac_deco=-1)

    # --- last_stop_depth ---
    def test_last_stop_depth_zero(self):
        with pytest.raises(ValueError, match="last_stop_depth must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, last_stop_depth=0)

    def test_last_stop_depth_negative(self):
        with pytest.raises(ValueError, match="last_stop_depth must be a positive finite number"):
            plan_dive(depth=30, bottom_time=20, last_stop_depth=-3)

    # --- Deco gas switch depths ---
    def test_deco_gas_switch_depth_zero(self):
        with pytest.raises(ValueError, match="must have a positive switch_depth"):
            plan_dive(
                depth=50,
                bottom_time=20,
                deco_gases=[Gas(50, 0, switch_depth=0)],
            )

    def test_deco_gas_switch_depth_exceeds_dive_depth(self):
        with pytest.raises(ValueError, match="must be less than dive depth"):
            plan_dive(
                depth=30,
                bottom_time=20,
                deco_gases=[Gas(50, 0, switch_depth=35)],
            )

    # --- Valid edge cases that should NOT raise ---
    def test_valid_simple_air_dive(self):
        """Basic sanity: a normal air dive should still work."""
        result = plan_dive(depth=30, bottom_time=30, gf=(30, 85))
        assert result.runtime > 0
        assert result.max_depth == 30

    def test_valid_trimix_with_deco_gases(self):
        """Full trimix setup should still work."""
        result = plan_dive(
            depth=50,
            bottom_time=25,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
            gf=(30, 85),
        )
        assert result.runtime > 0
        assert len(result.stops) > 0

    # --- PO2 safety validation ---
    def test_deco_gas_po2_exceeds_max(self):
        """O2 at 30m (PO2 ~4.0) should be rejected with default max_po2."""
        with pytest.raises(ValueError, match="exceeds max_po2"):
            plan_dive(
                depth=60,
                bottom_time=20,
                deco_gases=[Gas(100, 0, switch_depth=30)],
                gf=(30, 85),
            )

    def test_deco_gas_po2_ean50_at_30m_rejected(self):
        """EAN50 at 30m has PO2 ~2.0, should be rejected."""
        with pytest.raises(ValueError, match="exceeds max_po2"):
            plan_dive(
                depth=60,
                bottom_time=20,
                deco_gases=[Gas(50, 0, switch_depth=30)],
                gf=(30, 85),
            )

    def test_deco_gas_po2_o2_at_6m_allowed(self):
        """O2 at 6m (PO2 ~1.61) should be allowed with default max_po2=1.61."""
        result = plan_dive(
            depth=40,
            bottom_time=20,
            deco_gases=[Gas(100, 0, switch_depth=6)],
            gf=(30, 85),
        )
        assert result.runtime > 0

    def test_deco_gas_po2_custom_limit(self):
        """Custom max_po2 should override the default."""
        # O2 at 6m (PO2 ~1.61) rejected with max_po2=1.4
        with pytest.raises(ValueError, match="exceeds max_po2"):
            plan_dive(
                depth=40,
                bottom_time=20,
                deco_gases=[Gas(100, 0, switch_depth=6)],
                gf=(30, 85),
                max_po2=1.4,
            )

    def test_deco_gas_po2_high_limit_allows_deep_switch(self):
        """Higher max_po2 allows deeper switches for advanced users."""
        result = plan_dive(
            depth=60,
            bottom_time=20,
            deco_gases=[Gas(50, 0, switch_depth=21)],
            gf=(30, 85),
            max_po2=2.0,
        )
        assert result.runtime > 0

    # --- max_deco_time ---
    def test_max_deco_time_exceeded(self):
        """Deco time exceeding max_deco_time raises ValueError."""
        with pytest.raises(ValueError, match="exceeds max_deco_time"):
            plan_dive(depth=40, bottom_time=30, gf=(30, 85), max_deco_time=5)

    def test_max_deco_time_not_triggered_for_ndl(self):
        """NDL dive with zero deco doesn't trigger max_deco_time."""
        result = plan_dive(depth=10, bottom_time=5, max_deco_time=1)
        assert result.total_deco_time == 0.0
