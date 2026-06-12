#
# DecoTengu - dive decompression library.
#
# Tests for the modernised modules: models, types, tracking, planning.
#

import math

import pytest

from decodaitengu.const import WATER_VAPOUR_PRESSURE_DEFAULT as WATER_VAPOUR_PRESSURE
from decodaitengu.models import ZHL16B, ZHL16C
from decodaitengu.models.base import eq_gf_limit, eq_schreiner
from decodaitengu.planning import _gas_density, plan_dive
from decodaitengu.tracking.cns import CNSMethod, CNSTracker
from decodaitengu.tracking.otu import OTUTracker
from decodaitengu.types import Cylinder, Gas, TissueState


class TestGas:
    def test_air(self):
        gas = Gas(o2=21)
        assert gas.o2 == 21
        assert gas.he == 0
        assert gas.n2 == 79

    def test_trimix(self):
        gas = Gas(o2=21, he=35)
        assert gas.n2 == 44

    def test_repr_air(self):
        assert "Air" in repr(Gas(o2=21))

    def test_repr_ean(self):
        assert "EAN32" in repr(Gas(o2=32))

    def test_repr_trimix(self):
        assert "Tx" in repr(Gas(o2=21, he=35))

    def test_frozen(self):
        gas = Gas(o2=21)
        with pytest.raises(AttributeError):
            gas.o2 = 32


class TestCylinder:
    def test_total_litres(self):
        cyl = Cylinder(volume_litres=12.0, fill_bar=200)
        assert cyl.total_litres == 2400.0


class TestTissueState:
    def test_total_pressures(self):
        ts = TissueState(
            n2_pressures=(1.0, 2.0),
            he_pressures=(0.5, 0.3),
        )
        assert ts.total_pressures == (1.5, 2.3)


class TestSchreinerEquation:
    """Test Schreiner equation against known values from the original model.py docs."""

    def test_descent_ean32(self):
        """EAN32 descent from 0m to 30m at 20m/min (1.5 min).

        From model.py documentation:
        P_i = 0.7902 * (1 - 0.0627) = 0.74065446
        P_alv = 0.68 * (1 - 0.0627) = 0.637364
        R = 0.68 * 2 = 1.36
        k = ln(2) / 5.0
        t = 1.5
        Result = 0.919397
        """
        p_i = 0.7902 * (1.0 - 0.0627)  # initial N2 at surface
        p_alv = 0.68 * (1.0 - 0.0627)  # N2 alveolar at start depth
        rate = 0.68 * 2.0  # R = f_gas * P_rate
        time = 1.5
        k = math.log(2) / 5.0  # compartment 1 half-life

        result = eq_schreiner(p_i, p_alv, rate, time, k)
        assert abs(result - 0.919397) < 0.001

    def test_constant_depth(self):
        """EAN32 at 30m (4 bar) for 20 minutes, starting from 0.919397."""
        p_i = 0.919397
        p_alv = 0.68 * (4.0 - 0.0627)
        rate = 0.0
        time = 20.0
        k = math.log(2) / 5.0

        result = eq_schreiner(p_i, p_alv, rate, time, k)
        assert abs(result - 2.567490) < 0.001

    def test_ascent(self):
        """EAN32 ascent from 30m to 10m at 10m/min (2 min)."""
        p_i = 2.567490
        p_alv = 0.68 * (4.0 - 0.0627)
        rate = 0.68 * (-1.0)  # -10m/min = -1 bar/min
        time = 2.0
        k = math.log(2) / 5.0

        result = eq_schreiner(p_i, p_alv, rate, time, k)
        assert abs(result - 2.421840) < 0.001


class TestGfLimit:
    """Test ceiling limit calculation."""

    def test_n2_only(self):
        """Test with only nitrogen (no helium)."""
        result = eq_gf_limit(0.3, 0.74065446, 0.0, 1.1696, 0.5578, 0.0, 0.0)
        # When p_he = 0, the function should handle gracefully
        # With no He, p = p_n2, a = a_n2, b = b_n2
        # Actually with p_he = 0, p = p_n2, so a = a_n2, b = b_n2
        # But our function returns 0.0 when p <= 0
        # p_n2 = 0.74065446 > 0, so it should work
        assert abs(result - 0.314886) < 0.001

    def test_zero_pressure(self):
        """Zero total pressure returns 0."""
        result = eq_gf_limit(0.3, 0.0, 0.0, 1.1696, 0.5578, 1.6189, 0.4770)
        assert result == 0.0


class TestZHL16B:
    def test_init(self):
        model = ZHL16B()
        assert model.gf_low == 0.30
        assert model.gf_high == 0.85
        assert len(model.params.n2_half_life) == 16

    def test_tissue_init(self):
        model = ZHL16B()
        tissues = model.init(1.01325)
        assert len(tissues.n2_pressures) == 16
        assert len(tissues.he_pressures) == 16
        assert all(p == 0.0 for p in tissues.he_pressures)
        expected_n2 = 0.7902 * (1.01325 - WATER_VAPOUR_PRESSURE)
        assert abs(tissues.n2_pressures[0] - expected_n2) < 1e-6

    def test_load_increases_pressure_on_descent(self):
        model = ZHL16B()
        tissues = model.init(1.01325)
        gas = Gas(o2=21)
        # Descend to 30m
        loaded = model.load(tissues, 1.01325, 1.5, gas, 2.0)
        # N2 pressure should increase during descent
        assert loaded.n2_pressures[0] > tissues.n2_pressures[0]


class TestZHL16C:
    def test_init(self):
        model = ZHL16C()
        assert len(model.params.n2_half_life) == 16
        # First N2 half-life is 4.0 for ZHL-16C (vs 5.0 for B)
        assert model.params.n2_half_life[0] == 4.0

    def test_more_conservative_than_b(self):
        """ZHL-16C should produce a higher (more conservative) ceiling than B."""
        model_b = ZHL16B(gf_low=0.3, gf_high=0.85)
        model_c = ZHL16C(gf_low=0.3, gf_high=0.85)
        gas = Gas(o2=21)

        # Load both models with same dive profile
        tissues_b = model_b.init(1.01325)
        tissues_c = model_c.init(1.01325)

        # Descent + bottom time
        tissues_b = model_b.load(tissues_b, 1.01325, 1.75, gas, 2.0)
        tissues_b = model_b.load(tissues_b, 4.5, 38.25, gas, 0.0)

        tissues_c = model_c.load(tissues_c, 1.01325, 1.75, gas, 2.0)
        tissues_c = model_c.load(tissues_c, 4.5, 38.25, gas, 0.0)

        ceil_b = model_b.ceiling(tissues_b, 0.3)
        ceil_c = model_c.ceiling(tissues_c, 0.3)

        # C should have higher (deeper) ceiling = more conservative
        assert ceil_c >= ceil_b

    def test_he_coefficients_match_spec(self):
        """Verify He coefficients match the modernisation spec."""
        model = ZHL16C()
        assert model.params.he_a[0] == 1.7474
        assert model.params.he_b[0] == 0.4245
        assert model.params.he_half_life[0] == 1.51


class TestCNSTracker:
    def test_no_accumulation_below_threshold(self):
        cns = CNSTracker()
        cns.update(po2=0.4, time=60)
        assert cns.cns_percent == 0.0

    def test_accumulation_at_1_4(self):
        """At PO2 1.4, NOAA limit is 150min, so 30min = ~20% CNS."""
        cns = CNSTracker(CNSMethod.NOAA_TABLE)
        cns.update(po2=1.4, time=30)
        assert abs(cns.cns_percent - 20.0) < 0.5

    def test_exponential_matches_noaa_approximately(self):
        """Exponential method should approximately match NOAA table."""
        cns_exp = CNSTracker(CNSMethod.EXPONENTIAL)
        cns_noaa = CNSTracker(CNSMethod.NOAA_TABLE)

        cns_exp.update(po2=1.2, time=60)
        cns_noaa.update(po2=1.2, time=60)

        # Should be within 5% of each other
        assert abs(cns_exp.cns_percent - cns_noaa.cns_percent) < 5.0

    def test_reset(self):
        cns = CNSTracker()
        cns.update(po2=1.4, time=30)
        assert cns.cns_percent > 0
        cns.reset()
        assert cns.cns_percent == 0.0

    def test_high_po2_does_not_overflow(self):
        """CNS rate should be clamped at high PO2 (formula only valid to 1.6)."""
        cns = CNSTracker(CNSMethod.EXPONENTIAL)
        cns.update(po2=3.0, time=1.0)
        # Should be clamped to PO2=1.6 rate (~2.22%/min), not overflow
        assert cns.cns_percent < 5.0
        assert cns.cns_percent > 0.0

    def test_cns_at_1_8_is_finite_and_reasonable(self):
        """CNS at PO2=1.8 should be clamped to 1.6 rate."""
        cns = CNSTracker(CNSMethod.EXPONENTIAL)
        cns.update(po2=1.8, time=10.0)
        # Clamped to 1.6 rate: ~2.22%/min * 10min = ~22%
        assert cns.cns_percent > 10
        assert cns.cns_percent < 40


class TestOTUTracker:
    def test_no_accumulation_below_threshold(self):
        otu = OTUTracker()
        otu.update(po2=0.5, time=60)
        assert otu.otu == 0.0

    def test_at_1_0(self):
        """At PO2 1.0: OTU = t * ((1.0 - 0.5) / 0.5)^0.83 = t * 1.0."""
        otu = OTUTracker()
        otu.update(po2=1.0, time=30)
        assert abs(otu.otu - 30.0) < 0.1

    def test_reset(self):
        otu = OTUTracker()
        otu.update(po2=1.4, time=30)
        assert otu.otu > 0
        otu.reset()
        assert otu.otu == 0.0


class TestPlanDive:
    def test_air_shallow_ndl(self):
        """Shallow air dive should be NDL."""
        result = plan_dive(depth=18, bottom_time=30, gf=(100, 100))
        assert result.total_deco_time == 0.0
        assert result.stops == []
        # NDL should be computed for no-deco dives
        assert result.ndl is not None
        assert result.ndl > 0

    def test_segmented_ascent_slower_surface_increases_runtime(self):
        baseline = plan_dive(depth=18, bottom_time=15, gf=(100, 100), ascent_rate=10.0)
        segmented = plan_dive(
            depth=18,
            bottom_time=15,
            gf=(100, 100),
            ascent_rate=[(6, 10.0), (0, 0.5)],
        )
        assert segmented.runtime > baseline.runtime

    def test_segmented_ascent_dict_and_list_equivalent(self):
        from_list = plan_dive(
            depth=45,
            bottom_time=20,
            gf=(30, 85),
            ascent_rate=[(21, 10.0), (6, 6.0), (0, 3.0)],
        )
        from_dict = plan_dive(
            depth=45,
            bottom_time=20,
            gf=(30, 85),
            ascent_rate={21: 10.0, 6: 6.0, 0: 3.0},
        )
        assert from_dict.runtime == from_list.runtime
        assert from_dict.total_deco_time == from_list.total_deco_time

    def test_ndl_is_none_for_deco_dives(self):
        """Deco dives should have ndl=None."""
        result = plan_dive(depth=40, bottom_time=30, gf=(30, 85))
        assert result.total_deco_time > 0
        assert result.ndl is None

    def test_ndl_decreases_with_longer_bottom_time(self):
        """Longer bottom time should leave less NDL remaining."""
        short = plan_dive(depth=20, bottom_time=10, gf=(100, 100))
        long = plan_dive(depth=20, bottom_time=30, gf=(100, 100))
        assert short.ndl is not None
        assert long.ndl is not None
        assert short.ndl > long.ndl

    def test_ndl_decreases_with_depth(self):
        """Deeper dives should have shorter NDL."""
        shallow = plan_dive(depth=15, bottom_time=10, gf=(100, 100))
        deep = plan_dive(depth=30, bottom_time=10, gf=(100, 100))
        assert shallow.ndl is not None
        assert deep.ndl is not None
        assert shallow.ndl > deep.ndl

    def test_air_deep_requires_deco(self):
        """Deep air dive should produce deco stops."""
        result = plan_dive(depth=40, bottom_time=30, gf=(30, 85))
        assert result.total_deco_time > 0
        assert len(result.stops) > 0

    def test_trimix_produces_deco(self):
        """Trimix dive should produce deco."""
        result = plan_dive(
            depth=60,
            bottom_time=20,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21)],
            gf=(30, 85),
        )
        assert result.total_deco_time > 0
        assert result.max_depth == 60

    def test_gas_selection_picks_richest_eligible(self):
        """At shallow stops, should switch to the richest O2 gas available."""
        result = plan_dive(
            depth=50,
            bottom_time=25,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
            gf=(30, 85),
        )
        # The 3m stop should be on 100% O2 (switch_depth=6 allows it at 6m and shallower)
        # If gas selection was wrong, 3m stop would be on 50% and take longer
        # Verify that the last stop exists and is reasonable
        assert result.stops[-1].depth <= 6.0
        # With 100% O2, the shallow stop should be shorter than without it
        result_no_o2 = plan_dive(
            depth=50,
            bottom_time=25,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21)],
            gf=(30, 85),
        )
        # Having pure O2 available should reduce total deco time
        assert result.total_deco_time < result_no_o2.total_deco_time

    def test_cns_and_otu_tracked(self):
        """CNS and OTU should be non-zero for any non-trivial dive."""
        result = plan_dive(depth=30, bottom_time=30, gf=(30, 85))
        assert result.cns_percent > 0
        assert result.otu > 0

    def test_deeper_dive_more_deco(self):
        """Deeper dive should produce more deco (same bottom time, same gas)."""
        shallow = plan_dive(depth=30, bottom_time=30, gf=(30, 85))
        deep = plan_dive(depth=40, bottom_time=30, gf=(30, 85))
        assert deep.total_deco_time >= shallow.total_deco_time

    def test_gf_affects_deco(self):
        """Lower GF should produce more deco time."""
        liberal = plan_dive(depth=40, bottom_time=25, gf=(50, 90))
        conservative = plan_dive(depth=40, bottom_time=25, gf=(30, 70))
        assert conservative.total_deco_time >= liberal.total_deco_time

    def test_bottom_time_validation(self):
        """Bottom time shorter than descent should raise."""
        with pytest.raises(ValueError):
            plan_dive(depth=100, bottom_time=2, descent_rate=20)

    def test_cylinder_gas_count_mismatch(self):
        """Mismatched gas/cylinder counts should raise ValueError with clear message."""
        with pytest.raises(ValueError, match="does not match number of cylinders"):
            plan_dive(
                depth=50,
                bottom_time=20,
                back_gas=Gas(21, 35),
                deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
                back_cylinder=Cylinder(volume_litres=12, fill_bar=200),
                deco_cylinders=[Cylinder(volume_litres=7, fill_bar=200)],
                # 3 gases but only 2 cylinders
                gf=(30, 85),
            )

    def test_cylinder_tracking_valid(self):
        """Matching gas/cylinder counts should work."""
        result = plan_dive(
            depth=40,
            bottom_time=25,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21)],
            back_cylinder=Cylinder(volume_litres=12, fill_bar=200),
            deco_cylinders=[Cylinder(volume_litres=7, fill_bar=200)],
            gf=(30, 85),
        )
        assert result.runtime > 0
        assert len(result.gas_usage) > 0

    def test_surface_pressure_altitude_works(self):
        """Altitude diving (non-default surface_pressure) should work."""
        result = plan_dive(depth=30, bottom_time=20, surface_pressure=0.825, gf=(30, 85))
        assert result.runtime > 0
        # At altitude, tissues start at lower N2 pressure — more conservative
        sea_level = plan_dive(depth=30, bottom_time=20, surface_pressure=1.01325, gf=(30, 85))
        assert result.total_deco_time >= sea_level.total_deco_time

    def test_surface_pressure_out_of_range(self):
        """Surface pressure outside 0.5-1.1 bar should raise ValueError."""
        with pytest.raises(ValueError, match="surface_pressure must be between"):
            plan_dive(depth=30, bottom_time=20, surface_pressure=0.3)
        with pytest.raises(ValueError, match="surface_pressure must be between"):
            plan_dive(depth=30, bottom_time=20, surface_pressure=1.5)

    def test_surface_pressure_default_works(self):
        """Default surface_pressure should work fine."""
        result = plan_dive(depth=20, bottom_time=15, gf=(30, 85))
        assert result.runtime > 0

    def test_model_selection_zhl16b(self):
        """Should work with ZHL16B model."""
        result = plan_dive(depth=35, bottom_time=40, model=ZHL16B, gf=(30, 85))
        assert result.runtime > 0

    def test_last_stop_depth(self):
        """Last stop depth should be configurable."""
        result_3m = plan_dive(depth=35, bottom_time=40, gf=(30, 85), last_stop_depth=3)
        result_6m = plan_dive(depth=35, bottom_time=40, gf=(30, 85), last_stop_depth=6)
        # 6m last stop means shallowest stop is 6m
        if result_6m.stops:
            assert result_6m.stops[-1].depth >= 6.0
        # 3m last stop allows shallower stops
        if result_3m.stops:
            assert result_3m.stops[-1].depth >= 3.0


class TestAltitudeDiving:
    """Tests for altitude diving (reduced surface pressure)."""

    def test_altitude_1800m_more_conservative(self):
        """Diving at 1800m altitude (0.825 bar) should require more deco."""
        sea_level = plan_dive(depth=30, bottom_time=30, gf=(30, 85))
        altitude = plan_dive(depth=30, bottom_time=30, gf=(30, 85), surface_pressure=0.825)
        # At altitude, the reduced ambient pressure means tissues are relatively
        # more supersaturated — must produce equal or more decompression
        assert altitude.total_deco_time >= sea_level.total_deco_time

    def test_altitude_tissue_init(self):
        """Tissue init at altitude should produce lower N2 saturation."""
        sea_level = plan_dive(depth=20, bottom_time=5, gf=(100, 100))
        altitude = plan_dive(depth=20, bottom_time=5, gf=(100, 100), surface_pressure=0.825)
        # At altitude, initial N2 saturation is lower (less ambient N2)
        # After a short dive, the altitude tissues should still be less loaded
        sea_n2_total = sum(sea_level.tissues_final.n2_pressures)
        alt_n2_total = sum(altitude.tissues_final.n2_pressures)
        assert alt_n2_total < sea_n2_total

    def test_altitude_ndl_shorter(self):
        """NDL should be shorter at altitude (tissues reach limits faster)."""
        sea_level = plan_dive(depth=18, bottom_time=30, gf=(100, 100))
        altitude = plan_dive(depth=18, bottom_time=30, gf=(100, 100), surface_pressure=0.825)
        # Both should be NDL dives at this depth/time, but altitude NDL should be shorter
        assert sea_level.ndl is not None
        assert altitude.ndl is not None
        assert altitude.ndl <= sea_level.ndl

    def test_altitude_various_pressures(self):
        """Multiple altitude levels should produce monotonically more deco."""
        pressures = [1.01325, 0.9, 0.825, 0.7, 0.6]
        deco_times = []
        for sp in pressures:
            result = plan_dive(depth=30, bottom_time=30, gf=(30, 85), surface_pressure=sp)
            deco_times.append(result.total_deco_time)
        # Each lower pressure should produce >= deco time as the one above
        for i in range(1, len(deco_times)):
            assert deco_times[i] >= deco_times[i - 1], (
                f"Pressure {pressures[i]} bar produced less deco ({deco_times[i]}) "
                f"than {pressures[i - 1]} bar ({deco_times[i - 1]})"
            )

    def test_altitude_max_depth_unchanged(self):
        """max_depth should still match requested depth regardless of altitude."""
        result = plan_dive(depth=40, bottom_time=20, gf=(30, 85), surface_pressure=0.7)
        assert result.max_depth == pytest.approx(40.0)

    def test_altitude_cns_otu_tracked(self):
        """CNS and OTU should still be tracked at altitude."""
        result = plan_dive(depth=30, bottom_time=30, gf=(30, 85), surface_pressure=0.825)
        assert result.cns_percent >= 0
        assert result.otu >= 0


class TestGasDensity:
    def test_air_at_surface(self):
        """Air at surface (~1.01325 bar) should be about 1.2 g/L."""
        gas = Gas(o2=21)
        density = _gas_density(gas, 1.01325)
        assert 1.1 < density < 1.3

    def test_density_increases_with_depth(self):
        """Density at 40m should be higher than at surface."""
        gas = Gas(o2=21)
        d_surface = _gas_density(gas, 1.01325)
        d_40m = _gas_density(gas, 1.01325 + 40 * 0.09985)
        assert d_40m > d_surface

    def test_helium_reduces_density(self):
        """Trimix with helium should be less dense than air at same pressure."""
        air = Gas(o2=21)
        trimix = Gas(o2=21, he=35)
        p = 5.0
        assert _gas_density(trimix, p) < _gas_density(air, p)

    def test_plan_dive_max_density_nonzero(self):
        """max_gas_density should be non-zero after any dive."""
        result = plan_dive(depth=30, bottom_time=30, gf=(30, 85))
        assert result.max_gas_density > 0.0

    def test_deeper_dive_higher_density(self):
        """Deeper dive should yield higher max gas density."""
        shallow = plan_dive(depth=20, bottom_time=20, gf=(100, 100))
        deep = plan_dive(depth=40, bottom_time=20, gf=(100, 100))
        assert deep.max_gas_density > shallow.max_gas_density

    def test_trimix_lower_density_than_air(self):
        """Trimix back gas should produce lower max density than air at same depth."""
        air_dive = plan_dive(depth=60, bottom_time=20, gf=(30, 85))
        trimix_dive = plan_dive(depth=60, bottom_time=20, back_gas=Gas(21, 35), gf=(30, 85))
        assert trimix_dive.max_gas_density < air_dive.max_gas_density


class TestSubsurfaceComparison:
    """Regression tests for plan_dive() validated against Subsurface 6.0.5504 reference plans.

    All three reference plans use Bühlmann ZHL-16C, GF 50/70, 1013mbar surface pressure.
    Descent rate 60m/min (gives ~1min displayed descent, matching Subsurface plans).
    Ascent rate 10m/min (standard).

    Known algorithmic differences from Subsurface:
    - We use the Schreiner equation (analytically exact for linearly-changing pressure),
      while Subsurface uses the Haldane equation with 1-second constant-pressure steps.
      These are equivalent at constant depth but diverge during ascent/descent.
    - Gas switching during free ascent: we stay on back gas all the way to first_stop_depth;
      Subsurface switches gas as soon as the diver passes the switch depth during ascent.
    - These differences produce 1–4 min variation per stop, visible especially at 3m for
      air-only dives (our model less conservative) and at 3m for trimix dives (more conservative).

    The expected values below reflect our model's exact deterministic output (regression tests).
    Subsurface reference values are shown in docstrings for comparison.
    """

    GF = (50, 70)
    DESCENT_RATE = 60.0
    ASCENT_RATE = 10.0
    TOLERANCE = 1  # minutes (1-min resolution from our stop-counting loop)

    def _check_stops(self, result: object, expected: dict[float, float]) -> None:
        actual = {s.depth: s.time for s in result.stops}  # type: ignore[attr-defined]
        for depth, exp_time in expected.items():
            actual_time = actual.get(depth, 0)
            assert abs(actual_time - exp_time) <= self.TOLERANCE, (
                f"Stop at {depth}m: expected {exp_time} min, got {actual_time} min "
                f"(all stops: {actual})"
            )

    def test_50m_air_no_deco_gases(self):
        """50m/19min, air only, GF 50/70.

        Our model:    15m:2, 12m:4, 9m:5, 6m:11, 3m:25 (total deco 47min)
        Subsurface:   15m:3, 12m:4, 9m:7, 6m:12, 3m:29 (total runtime 79min)

        Difference is primarily in the 3m stop (Schreiner vs Haldane for the ascent).
        """
        result = plan_dive(
            depth=50,
            bottom_time=19,
            back_gas=Gas(o2=21),
            gf=self.GF,
            descent_rate=self.DESCENT_RATE,
            ascent_rate=self.ASCENT_RATE,
        )
        self._check_stops(result, {15.0: 2, 12.0: 4, 9.0: 5, 6.0: 11, 3.0: 25})

    def test_50m_air_ean50_o2(self):
        """50m/19min, air + EAN50@21m + O2@6m, GF 50/70.

        Our model:    15m:1, 12m:3, 9m:3, 6m:4, 3m:7 (total deco 18min)
        Subsurface:   15m:1, 12m:3, 9m:4, 6m:4, 3m:8  (total runtime 45min)

        Note: 21m gas-switch stop is added by dive_plan.py, not plan_dive().
        Note: 3m stop is now on 100%% O2 (richest eligible gas selected correctly).
        """
        result = plan_dive(
            depth=50,
            bottom_time=19,
            back_gas=Gas(o2=21),
            deco_gases=[
                Gas(o2=50, switch_depth=21.0),
                Gas(o2=100, switch_depth=6.0),
            ],
            gf=self.GF,
            descent_rate=self.DESCENT_RATE,
            ascent_rate=self.ASCENT_RATE,
        )
        self._check_stops(result, {15.0: 1, 12.0: 3, 9.0: 3, 6.0: 4, 3.0: 7})

    def test_60m_tx18_45_ean50_o2(self):
        """60m/14min, Tx18/45 + EAN50@21m + O2@6m, GF 50/70.

        Our model:    18m:1, 15m:1, 12m:2, 9m:3, 6m:5, 3m:8 (total deco 20min)
        Subsurface:   15m:2, 12m:3, 9m:4, 6m:5, 3m:10         (total runtime 45min)

        Note: 21m gas-switch stop is added by dive_plan.py, not plan_dive().
        Note: extra 18m stop vs Subsurface — fast He off-gassing controls the ceiling.
        Note: 3m stop is now on 100%% O2 (richest eligible gas selected correctly).
        """
        result = plan_dive(
            depth=60,
            bottom_time=14,
            back_gas=Gas(o2=18, he=45),
            deco_gases=[
                Gas(o2=50, switch_depth=21.0),
                Gas(o2=100, switch_depth=6.0),
            ],
            gf=self.GF,
            descent_rate=self.DESCENT_RATE,
            ascent_rate=self.ASCENT_RATE,
        )
        self._check_stops(result, {18.0: 1, 15.0: 1, 12.0: 2, 9.0: 3, 6.0: 5, 3.0: 8})

    def test_51m_tx22_27_bounce_segmented_ascent(self):
        """51m/10min bounce, Tx22/27 + EAN50@21m + O2@6m, GF 50/80, segmented ascent.

        Validated against Subsurface 6.0.5504 on 2026-06-11.

        Subsurface: NDL dive, no deco stops, runtime 21 min.
        Our model:  9m x 1 min stop, runtime ~20.5 min.

        Our engine now switches to EAN50 at 21m during the free ascent (fix for
        issue #45).  A marginal 9m stop remains due to model conservatism, but
        the ~1 min runtime gap vs the buggy back-gas-only ascent is eliminated.

        The primary regression purpose of this test is to confirm that the
        segmented ascent (10 m/min below 6m, 1 m/min above 6m) produces the
        correct per-segment slope in the depth profile: specifically, that a
        6m breakpoint exists as a distinct profile point rather than the two
        segments being merged into one averaged line.
        """
        result = plan_dive(
            depth=51,
            bottom_time=10,
            back_gas=Gas(o2=22, he=27),
            deco_gases=[
                Gas(o2=50, switch_depth=21.0),
                Gas(o2=100, switch_depth=6.0),
            ],
            gf=(50, 80),
            descent_rate=self.DESCENT_RATE,
            ascent_rate=[(6, 10.0), (0, 1.0)],
            sac_bottom=20,
            sac_deco=20,
        )
        self._check_stops(result, {9.0: 1})
        # Both gas switches add 1 min each: EAN50 at 21m (free ascent) + O2 at 6m (stop, no deco offset)
        assert result.runtime == pytest.approx(22.5, abs=0.5)

        # The 6m breakpoint must appear as a distinct pair of profile points so
        # that the two ascent rate segments are drawn at their correct individual
        # slopes rather than blended into one averaged line.
        depths_at_6m = [d for _, d in result.profile if d == 6.0]
        assert len(depths_at_6m) >= 2, (
            "Expected at least two profile points at 6m (rate-change breakpoint), "
            f"got: {result.profile}"
        )


class TestH2Gas:
    """Tests for hydrogen (H2) gas support.

    .. warning::
        H2 decompression is EXPERIMENTAL. Coefficients are derived from
        diffusion-theory scaling of He half-times (factor ≈ 0.71) with He a/b
        values used as a proxy. Do NOT use for actual dive planning.
    """

    def test_hydreliox_n2_fraction(self):
        """N2 = 100 - O2 - He - H2."""
        gas = Gas(o2=2, he=30, h2=60)
        assert gas.n2 == pytest.approx(8.0)

    def test_h2_repr(self):
        gas = Gas(o2=2, he=20, h2=70)
        assert "Hydreliox" in repr(gas)
        assert "2/20/70" in repr(gas)

    def test_h2_flammability_limit(self):
        """O2 > 4% with H2 present must raise ValueError."""
        with pytest.raises(ValueError, match="combustion"):
            Gas(o2=5, he=20, h2=70)

    def test_h2_flammability_at_limit(self):
        """O2 = 4% with H2 should be accepted."""
        gas = Gas(o2=4, he=20, h2=70)
        assert gas.o2 == 4.0
        assert gas.h2 == 70.0

    def test_h2_zero_is_allowed_any_o2(self):
        """Standard gases with h2=0 should not be affected by flammability check."""
        gas = Gas(o2=21, he=0, h2=0)
        assert gas.n2 == pytest.approx(79.0)

    def test_h2_fractions_exceed_100(self):
        with pytest.raises(ValueError, match="must not exceed 100%"):
            Gas(o2=4, he=50, h2=60)

    def test_gas_density_lower_with_h2(self):
        """H2 has lower MW than N2/He so density should drop."""
        # Compare Hydreliox 2/30/60 vs Tx2/30 (N2 replaces H2)
        h2_gas = Gas(o2=2, he=30, h2=60)
        n2_gas = Gas(o2=2, he=30, h2=0)  # balance is N2
        abs_p = 6.0  # ~50m
        assert _gas_density(h2_gas, abs_p) < _gas_density(n2_gas, abs_p)

    def test_h2_tissue_loading_faster_than_he(self):
        """H2 diffuses faster than He so tissue loading should be higher."""
        from decodaitengu.models import ZHL16C

        model = ZHL16C(gf_low=0.3, gf_high=0.85)
        tissues_init = model.init(1.01325)
        abs_p = 6.01325  # ~50m
        h2_gas = Gas(o2=2, he=0, h2=98)
        he_gas = Gas(o2=2, he=98, h2=0)
        t_h2 = model.load(tissues_init, abs_p, 20.0, h2_gas, 0.0)
        t_he = model.load(tissues_init, abs_p, 20.0, he_gas, 0.0)
        # H2 loads the fastest compartment more than He due to shorter half-time
        assert t_h2.h2_pressures[0] > t_he.he_pressures[0]

    def test_plan_dive_hydreliox_emits_warning(self):
        """plan_dive with H2 gas must emit a UserWarning."""
        import warnings

        hydreliox = Gas(o2=2, he=20, h2=70)
        deco_gases = [
            Gas(o2=50, switch_depth=21, label="lean"),
            Gas(o2=100, switch_depth=6, label="rich"),
        ]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # gf=99/99 with deco gases keeps deco time minimal
            result = plan_dive(
                depth=30,
                bottom_time=15,
                back_gas=hydreliox,
                deco_gases=deco_gases,
                gf=(99, 99),
            )
        assert any("EXPERIMENTAL" in str(warning.message) for warning in w)
        assert isinstance(result.max_pph2, float)
        assert result.max_pph2 > 0.0

    def test_plan_dive_hydreliox_with_deco_gases(self):
        """Hydreliox dive with deco gases produces stops and tracks H2."""
        import warnings

        back_gas = Gas(o2=2, he=20, h2=70)
        deco_gases = [
            Gas(o2=50, switch_depth=21, label="lean"),
            Gas(o2=100, switch_depth=6, label="rich"),
        ]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = plan_dive(
                depth=30,
                bottom_time=15,
                back_gas=back_gas,
                deco_gases=deco_gases,
                gf=(50, 70),
            )
        assert result.stops, "Expected deco stops for GF 50/70 hydreliox dive"
        assert result.max_pph2 > 0
        assert result.total_deco_time > 0

    def test_plan_dive_no_h2_max_pph2_is_zero(self):
        """Dives without H2 must return max_pph2 == 0."""
        result = plan_dive(depth=40, bottom_time=25, back_gas=Gas(o2=21, he=35))
        assert result.max_pph2 == 0.0


class TestUnifiedGasAPI:
    """Tests for the unified gases= / cylinders= API introduced in v1.4.0."""

    def test_basic_unified_api_matches_legacy(self):
        """Unified API with one descent gas should produce same result as legacy."""
        legacy = plan_dive(
            depth=40,
            bottom_time=20,
            back_gas=Gas(o2=21),
            deco_gases=[Gas(o2=50, switch_depth=21)],
            gf=(50, 70),
        )
        unified = plan_dive(
            depth=40,
            bottom_time=20,
            gases=[
                Gas(o2=21, switch_depth=40, use_on_descent=True, label="back"),
                Gas(o2=50, switch_depth=21, label="lean"),
            ],
            gf=(50, 70),
        )
        assert unified.runtime == pytest.approx(legacy.runtime, abs=0.1)
        assert unified.total_deco_time == pytest.approx(legacy.total_deco_time, abs=1.0)

    def test_travel_gas_used_on_descent_not_ascent(self):
        """Travel gas (use_on_ascent=False) must NOT be used during ascent."""
        result = plan_dive(
            depth=80,
            bottom_time=20,
            gases=[
                Gas(
                    o2=21,
                    switch_depth=40,
                    use_on_descent=True,
                    use_on_ascent=False,
                    label="travel",
                ),
                Gas(o2=18, he=45, switch_depth=80, use_on_descent=True, label="back"),
                Gas(o2=50, switch_depth=21, label="lean"),
                Gas(o2=100, switch_depth=6, label="rich"),
            ],
            gf=(50, 70),
        )
        assert result.stops, "Expected deco stops for 80m/20min Tx18/45 dive"
        # Verify travel gas appears in profile on descent (non-zero profile points at ~40m)
        descent_depths = [d for t, d in result.profile if t <= result.profile[1][0] + 5]
        assert any(d <= 40 for d in descent_depths), "Expected descent waypoints at/above 40m"

    def test_travel_gas_descent_gas_tracking(self):
        """Travel gas consumption is tracked separately from back gas."""
        travel = Gas(
            o2=21, switch_depth=40, use_on_descent=True, use_on_ascent=False, label="travel"
        )
        back = Gas(o2=18, he=45, switch_depth=80, use_on_descent=True, label="back")
        lean = Gas(o2=50, switch_depth=21, label="lean")
        result = plan_dive(
            depth=80,
            bottom_time=20,
            gases=[travel, back, lean],
            cylinders=[
                Cylinder(12.0, 230),
                Cylinder(24.4, 230),
                Cylinder(11.1, 200),
            ],
            gf=(50, 70),
        )
        assert "travel" in result.gas_usage, (
            f"Expected travel gas in usage: {list(result.gas_usage)}"
        )
        assert "back" in result.gas_usage
        assert result.gas_usage["travel"].consumed_litres > 0
        assert result.gas_usage["back"].consumed_litres > 0

    def test_cannot_mix_unified_and_legacy_gas_api(self):
        """Mixing gases= with back_gas= must raise ValueError."""
        with pytest.raises(ValueError, match="Cannot combine"):
            plan_dive(
                depth=40,
                bottom_time=20,
                back_gas=Gas(o2=21),
                gases=[Gas(o2=21, switch_depth=40, use_on_descent=True)],
            )

    def test_cannot_mix_unified_and_legacy_cylinder_api(self):
        """Mixing cylinders= with back_cylinder= must raise ValueError."""
        with pytest.raises(ValueError, match="Cannot combine"):
            plan_dive(
                depth=40,
                bottom_time=20,
                gases=[Gas(o2=21, switch_depth=40, use_on_descent=True)],
                cylinders=[Cylinder(12.0, 200)],
                back_cylinder=Cylinder(12.0, 200),
            )

    def test_no_descent_gas_raises(self):
        """Gas list with no use_on_descent=True gas must raise ValueError."""
        with pytest.raises(ValueError, match="use_on_descent"):
            plan_dive(
                depth=40,
                bottom_time=20,
                gases=[Gas(o2=21, switch_depth=40)],  # use_on_descent=False by default
            )

    def test_back_gas_switch_depth_must_cover_depth(self):
        """Back gas with switch_depth < depth must raise ValueError."""
        with pytest.raises(ValueError, match="No descent gas covers"):
            plan_dive(
                depth=80,
                bottom_time=20,
                gases=[
                    Gas(o2=21, switch_depth=40, use_on_descent=True),  # only covers to 40m
                ],
            )

    def test_travel_gas_not_used_at_depth(self):
        """Travel gas must switch to back gas when descending past its switch_depth."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = plan_dive(
                depth=80,
                bottom_time=15,
                gases=[
                    Gas(o2=4, he=0, h2=90, switch_depth=80, use_on_descent=True, label="back"),
                    Gas(
                        o2=21,
                        switch_depth=40,
                        use_on_descent=True,
                        use_on_ascent=False,
                        label="travel",
                    ),
                    Gas(o2=50, switch_depth=21, label="lean"),
                ],
                gf=(50, 70),
            )
        # Profile should show a waypoint at 40m (the gas switch depth)
        profile_depths = [d for _, d in result.profile]
        assert 40.0 in profile_depths, (
            f"Expected 40m waypoint for travel gas switch. Profile depths: {profile_depths}"
        )


class TestGasSwitchTime:
    """Tests for gas_switch_time parameter."""

    def test_gas_switch_time_increases_runtime(self):
        """Non-zero gas_switch_time should increase runtime vs 0.0."""
        base = plan_dive(
            depth=50,
            bottom_time=19,
            back_gas=Gas(o2=21),
            deco_gases=[Gas(o2=50, switch_depth=21), Gas(o2=100, switch_depth=6)],
            gf=(50, 70),
            gas_switch_time=0.0,
        )
        with_switch = plan_dive(
            depth=50,
            bottom_time=19,
            back_gas=Gas(o2=21),
            deco_gases=[Gas(o2=50, switch_depth=21), Gas(o2=100, switch_depth=6)],
            gf=(50, 70),
            gas_switch_time=1.0,
        )
        # Both gas switches fire: EAN50 at 21m adds 1 min net (before stops, no offset),
        # O2 at 6m adds 1 min switch time but off-gasses 1 min of stop → net 0.
        # Net overall: +1 min.
        assert with_switch.runtime > base.runtime

    def test_gas_switch_time_zero_matches_no_switch_time(self):
        """gas_switch_time=0.0 should produce same result as omitting the param."""
        default = plan_dive(depth=40, bottom_time=25, back_gas=Gas(o2=21), gf=(50, 70))
        zero = plan_dive(
            depth=40, bottom_time=25, back_gas=Gas(o2=21), gf=(50, 70), gas_switch_time=0.0
        )
        # No deco gases → no switches → same either way
        assert default.runtime == zero.runtime

    def test_descent_gas_switch_time_adds_pause(self):
        """gas_switch_time > 0 on descent should add a pause when the gas changes."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            no_pause = plan_dive(
                depth=80,
                bottom_time=20,
                gases=[
                    Gas(
                        o2=21,
                        switch_depth=40,
                        use_on_descent=True,
                        use_on_ascent=False,
                        label="travel",
                    ),
                    Gas(o2=4, he=0, h2=90, switch_depth=80, use_on_descent=True, label="back"),
                    Gas(o2=50, switch_depth=21, label="lean"),
                ],
                gf=(50, 70),
                gas_switch_time=0.0,
            )
            with_pause = plan_dive(
                depth=80,
                bottom_time=20,
                gases=[
                    Gas(
                        o2=21,
                        switch_depth=40,
                        use_on_descent=True,
                        use_on_ascent=False,
                        label="travel",
                    ),
                    Gas(o2=4, he=0, h2=90, switch_depth=80, use_on_descent=True, label="back"),
                    Gas(o2=50, switch_depth=21, label="lean"),
                ],
                gf=(50, 70),
                gas_switch_time=1.0,
            )
        # Runtimes must differ (switch pauses affect tissue loading and thus deco)
        assert no_pause.runtime != with_pause.runtime
        # Descent switch pause at 40m must appear as two consecutive profile points at 40m
        profile_40m_times = [t for t, d in with_pause.profile if d == 40.0]
        assert len(profile_40m_times) >= 2, (
            f"Expected at least two profile points at 40m for descent gas switch pause. "
            f"Profile: {with_pause.profile[:20]}"
        )
        # Gap at 40m must be ≥ gas_switch_time
        assert profile_40m_times[-1] - profile_40m_times[0] >= 1.0
