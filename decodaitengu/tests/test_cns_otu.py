#
# DecoTengu - dive decompression library.
#
# Comprehensive CNS and OTU tracking tests (Issue #6: H3).
#

import pytest

from decodaitengu.tracking.cns import (
    CNSMethod,
    CNSTracker,
    _exponential_cns_rate,
    _noaa_time_limit,
)
from decodaitengu.tracking.otu import OTUTracker


class TestNOAATimeLimit:
    """Test the NOAA table lookup and interpolation."""

    def test_below_threshold_returns_inf(self):
        """PO2 <= 0.5 returns infinity (no CNS concern)."""
        assert _noaa_time_limit(0.5) == float("inf")
        assert _noaa_time_limit(0.3) == float("inf")
        assert _noaa_time_limit(0.0) == float("inf")

    def test_exact_table_entries(self):
        """Exact NOAA table values (2014)."""
        assert _noaa_time_limit(0.6) == 720.0
        assert _noaa_time_limit(1.0) == 300.0
        assert _noaa_time_limit(1.4) == 150.0
        assert _noaa_time_limit(1.6) == 45.0

    def test_interpolation_between_entries(self):
        """Linear interpolation between table entries."""
        # Between 1.0 (300min) and 1.1 (240min): midpoint should be 270
        limit = _noaa_time_limit(1.05)
        assert abs(limit - 270.0) < 0.1

    def test_above_highest_entry(self):
        """PO2 above 1.6 should return the 1.6 limit (45 min)."""
        assert _noaa_time_limit(1.8) == 45.0
        assert _noaa_time_limit(2.0) == 45.0

    def test_monotonically_decreasing(self):
        """Higher PO2 should give shorter time limits."""
        po2_values = [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]
        limits = [_noaa_time_limit(p) for p in po2_values]
        for i in range(len(limits) - 1):
            assert limits[i] >= limits[i + 1], (
                f"Time limit not monotonically decreasing: "
                f"PO2={po2_values[i]}->{po2_values[i + 1]}, limit={limits[i]}->{limits[i + 1]}"
            )


class TestExponentialCNSRate:
    """Test the exponential CNS rate formula."""

    def test_below_threshold_returns_zero(self):
        """PO2 <= 0.5 should return zero rate."""
        assert _exponential_cns_rate(0.5) == 0.0
        assert _exponential_cns_rate(0.3) == 0.0
        assert _exponential_cns_rate(0.0) == 0.0

    def test_rate_always_non_negative(self):
        """Rate should never be negative for any valid PO2."""
        for po2_x10 in range(0, 30):
            po2 = po2_x10 / 10.0
            assert _exponential_cns_rate(po2) >= 0.0

    def test_rate_increases_with_po2(self):
        """Rate should generally increase with PO2 above threshold."""
        prev_rate = 0.0
        for po2_x10 in range(6, 17):  # 0.6 to 1.6
            po2 = po2_x10 / 10.0
            rate = _exponential_cns_rate(po2)
            assert rate >= prev_rate, (
                f"Rate not increasing: PO2={po2}, rate={rate}, prev={prev_rate}"
            )
            prev_rate = rate


class TestCNSMethodsAgreement:
    """Test that EXPONENTIAL and NOAA_TABLE methods agree within tolerance.

    This is the critical safety test: the exponential formula must track the
    auditable NOAA table within acceptable bounds across the full PO2 range.
    """

    @pytest.mark.parametrize(
        "po2",
        [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6],
    )
    def test_agreement_at_table_po2_values(self, po2: float) -> None:
        """At each NOAA table PO2 entry, 60 min exposure should agree within 15%."""
        time = 60.0

        cns_exp = CNSTracker(CNSMethod.EXPONENTIAL)
        cns_noaa = CNSTracker(CNSMethod.NOAA_TABLE)

        cns_exp.update(po2, time)
        cns_noaa.update(po2, time)

        # Both should be non-zero above threshold
        assert cns_exp.cns_percent > 0
        assert cns_noaa.cns_percent > 0

        # Agreement within 15% relative or 3% absolute (whichever is more lenient)
        diff = abs(cns_exp.cns_percent - cns_noaa.cns_percent)
        relative_diff = diff / max(cns_noaa.cns_percent, 0.01)
        assert relative_diff < 0.15 or diff < 3.0, (
            f"PO2={po2}: EXPONENTIAL={cns_exp.cns_percent:.2f}%, "
            f"NOAA={cns_noaa.cns_percent:.2f}%, diff={diff:.2f}%, "
            f"relative={relative_diff:.2%}"
        )

    @pytest.mark.parametrize(
        "po2",
        [0.65, 0.75, 0.85, 0.95, 1.05, 1.15, 1.25, 1.35, 1.45, 1.55],
    )
    def test_agreement_at_interpolated_po2_values(self, po2: float) -> None:
        """At midpoints between NOAA entries, methods should agree within 20%."""
        time = 60.0

        cns_exp = CNSTracker(CNSMethod.EXPONENTIAL)
        cns_noaa = CNSTracker(CNSMethod.NOAA_TABLE)

        cns_exp.update(po2, time)
        cns_noaa.update(po2, time)

        diff = abs(cns_exp.cns_percent - cns_noaa.cns_percent)
        relative_diff = diff / max(cns_noaa.cns_percent, 0.01)
        assert relative_diff < 0.20 or diff < 3.0, (
            f"PO2={po2}: EXPONENTIAL={cns_exp.cns_percent:.2f}%, "
            f"NOAA={cns_noaa.cns_percent:.2f}%, diff={diff:.2f}%, "
            f"relative={relative_diff:.2%}"
        )


class TestCNSTrackerEdgeCases:
    """Edge cases for CNSTracker."""

    def test_zero_time_no_accumulation(self):
        """Zero time should not accumulate any CNS."""
        cns = CNSTracker()
        cns.update(po2=1.4, time=0.0)
        assert cns.cns_percent == 0.0

    def test_negative_time_no_accumulation(self):
        """Negative time should not accumulate CNS."""
        cns = CNSTracker()
        cns.update(po2=1.4, time=-5.0)
        assert cns.cns_percent == 0.0

    def test_exactly_at_threshold(self):
        """PO2 exactly 0.5 should not accumulate."""
        cns = CNSTracker()
        cns.update(po2=0.5, time=60.0)
        assert cns.cns_percent == 0.0

    def test_just_above_threshold(self):
        """PO2 just above 0.5 should accumulate something."""
        cns = CNSTracker(CNSMethod.NOAA_TABLE)
        cns.update(po2=0.51, time=60.0)
        assert cns.cns_percent > 0.0

    def test_cumulative_tracking(self):
        """Multiple updates should accumulate."""
        cns = CNSTracker(CNSMethod.NOAA_TABLE)
        cns.update(po2=1.0, time=30.0)
        first = cns.cns_percent
        cns.update(po2=1.0, time=30.0)
        assert cns.cns_percent == pytest.approx(first * 2, abs=0.01)

    def test_noaa_full_exposure_reaches_100(self):
        """Full single-exposure limit should reach ~100% CNS."""
        cns = CNSTracker(CNSMethod.NOAA_TABLE)
        cns.update(po2=1.6, time=45.0)  # NOAA limit for 1.6 is 45 min
        assert abs(cns.cns_percent - 100.0) < 0.1

    def test_high_po2_accumulates_fast(self):
        """PO2 1.6 should accumulate faster than PO2 0.6."""
        cns_high = CNSTracker(CNSMethod.NOAA_TABLE)
        cns_low = CNSTracker(CNSMethod.NOAA_TABLE)
        cns_high.update(po2=1.6, time=10.0)
        cns_low.update(po2=0.6, time=10.0)
        assert cns_high.cns_percent > cns_low.cns_percent


class TestOTUTrackerEdgeCases:
    """Edge cases for OTUTracker."""

    def test_zero_time(self):
        otu = OTUTracker()
        otu.update(po2=1.4, time=0.0)
        assert otu.otu == 0.0

    def test_negative_time(self):
        otu = OTUTracker()
        otu.update(po2=1.4, time=-5.0)
        assert otu.otu == 0.0

    def test_at_threshold(self):
        """PO2 exactly 0.5 should produce 0 OTU."""
        otu = OTUTracker()
        otu.update(po2=0.5, time=60.0)
        assert otu.otu == 0.0

    def test_cumulative(self):
        """Multiple updates accumulate."""
        otu = OTUTracker()
        otu.update(po2=1.0, time=30.0)
        first = otu.otu
        otu.update(po2=1.0, time=30.0)
        assert otu.otu == pytest.approx(first * 2, abs=0.01)

    def test_higher_po2_more_otu(self):
        """Higher PO2 should produce more OTU for the same time."""
        otu_low = OTUTracker()
        otu_high = OTUTracker()
        otu_low.update(po2=1.0, time=30.0)
        otu_high.update(po2=1.6, time=30.0)
        assert otu_high.otu > otu_low.otu

    def test_known_value_at_po2_1_0(self):
        """At PO2 1.0: OTU = t * ((1.0 - 0.5) / 0.5)^0.83 = t * 1.0."""
        otu = OTUTracker()
        otu.update(po2=1.0, time=60.0)
        assert abs(otu.otu - 60.0) < 0.1
