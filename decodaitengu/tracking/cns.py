#
# DecoTengu - dive decompression library.
#
# Copyright (C) 2024 Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""CNS (Central Nervous System) oxygen toxicity tracking.

Supports two calculation methods:
- NOAA table: Linear interpolation between published single-exposure limits.
- Exponential (default): Uses the formula from the ScubaBoard reference,
  which provides continuous calculation without table lookup artefacts.

Reference:
    https://scubaboard.com/community/threads/need-an-excel-formula-that-will-calculate-cns.237903/post-10750263
"""

import math
from enum import Enum


class CNSMethod(Enum):
    """CNS calculation method selection."""

    EXPONENTIAL = "exponential"
    NOAA_TABLE = "noaa_table"


# NOAA single-exposure limits (2014)
# (PO2 threshold, time limit in minutes)
_NOAA_LIMITS: list[tuple[float, float]] = [
    (0.6, 720.0),
    (0.7, 570.0),
    (0.8, 450.0),
    (0.9, 360.0),
    (1.0, 300.0),
    (1.1, 240.0),
    (1.2, 210.0),
    (1.3, 180.0),
    (1.4, 150.0),
    (1.5, 120.0),
    (1.6, 45.0),
]


def _noaa_time_limit(po2: float) -> float:
    """Get NOAA single-exposure time limit for a given PO2.

    Linearly interpolates between table entries.

    :param po2: Partial pressure of oxygen [bar].
    :returns: Time limit in minutes. Returns infinity for PO2 <= 0.5.
    """
    if po2 <= 0.5:
        return float("inf")

    # Below the lowest table entry, extrapolate from first two entries
    if po2 <= _NOAA_LIMITS[0][0]:
        p1, t1 = _NOAA_LIMITS[0]
        p2, t2 = _NOAA_LIMITS[1]
        slope = (t2 - t1) / (p2 - p1)
        return t1 + slope * (po2 - p1)

    # Above the highest table entry, use highest limit
    if po2 >= _NOAA_LIMITS[-1][0]:
        return _NOAA_LIMITS[-1][1]

    # Interpolate between entries
    for i in range(len(_NOAA_LIMITS) - 1):
        p1, t1 = _NOAA_LIMITS[i]
        p2, t2 = _NOAA_LIMITS[i + 1]
        if p1 <= po2 <= p2:
            frac = (po2 - p1) / (p2 - p1)
            return t1 + frac * (t2 - t1)

    return _NOAA_LIMITS[-1][1]


def _exponential_cns_rate(po2: float) -> float:
    """Calculate CNS accumulation rate using exponential formula.

    Uses the compact formula from the ScubaBoard reference (pig, 2026) which provides
    a continuous smooth approximation of the NOAA limits without piecewise artefacts:

        rate = 0.39419*PO2^2 - 0.14119*PO2 + 0.08293
               + 0.00090*exp(30.05712*(PO2-1.35667)) / (1+exp(-120*(PO2-1.35667)))

    Returns CNS% accumulated per minute at the given PO2.
    The formula is only valid for PO2 in the range 0.5–1.6 bar; values above 1.6
    are clamped to the maximum NOAA rate to avoid exponential overflow.

    :param po2: Partial pressure of oxygen [bar].
    :returns: CNS% accumulated per minute at this PO2.
    """
    if po2 <= 0.5:
        return 0.0

    # Clamp to formula's valid domain to prevent exponential overflow.
    # The NOAA table only defines limits up to PO2=1.6; above that the
    # exponential term diverges rapidly. Clamping at 1.6 means any PO2 > 1.6
    # accumulates at the maximum NOAA rate (~2.22%/min = 100%/45min).
    clamped_po2 = min(po2, 1.6)

    # Smooth continuous formula matching NOAA limits
    x = clamped_po2 - 1.35667
    exp_term = 0.00090 * math.exp(30.05712 * x) / (1.0 + math.exp(-120.0 * x))
    rate = 0.39419 * clamped_po2 * clamped_po2 - 0.14119 * clamped_po2 + 0.08293 + exp_term
    return max(0.0, rate)


class CNSTracker:
    """Tracks CNS oxygen toxicity percentage across a dive.

    :param method: Calculation method to use. Default is EXPONENTIAL.
    """

    def __init__(self, method: CNSMethod = CNSMethod.EXPONENTIAL) -> None:
        self.method = method
        self.cns_percent: float = 0.0

    def reset(self) -> None:
        """Reset CNS tracking to zero."""
        self.cns_percent = 0.0

    def update(self, po2: float, time: float) -> None:
        """Update CNS accumulation for a segment of exposure.

        :param po2: Partial pressure of oxygen during segment [bar].
        :param time: Duration of segment [min].
        """
        if po2 <= 0.5 or time <= 0:
            return

        if self.method == CNSMethod.NOAA_TABLE:
            limit = _noaa_time_limit(po2)
            if limit > 0:
                self.cns_percent += (time / limit) * 100.0
        else:
            rate = _exponential_cns_rate(po2)
            self.cns_percent += rate * time
