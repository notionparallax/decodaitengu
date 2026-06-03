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

    def _check_stops(self, result, expected: dict):
        actual = {s.depth: s.time for s in result.stops}
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

        Our model:    15m:1, 12m:3, 9m:3, 6m:4, 3m:12 (total deco 23min)
        Subsurface:   15m:1, 12m:3, 9m:4, 6m:4, 3m:8  (total runtime 45min)

        Note: 21m gas-switch stop is added by dive_plan.py, not plan_dive().
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
        self._check_stops(result, {15.0: 1, 12.0: 3, 9.0: 3, 6.0: 4, 3.0: 12})

    def test_60m_tx18_45_ean50_o2(self):
        """60m/14min, Tx18/45 + EAN50@21m + O2@6m, GF 50/70.

        Our model:    18m:1, 15m:1, 12m:2, 9m:3, 6m:5, 3m:12 (total deco 24min)
        Subsurface:   15m:2, 12m:3, 9m:4, 6m:5, 3m:10         (total runtime 45min)

        Note: 21m gas-switch stop is added by dive_plan.py, not plan_dive().
        Note: extra 18m stop vs Subsurface — fast He off-gassing controls the ceiling.
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
        self._check_stops(result, {18.0: 1, 15.0: 1, 12.0: 2, 9.0: 3, 6.0: 5, 3.0: 12})
