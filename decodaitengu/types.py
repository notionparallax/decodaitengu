#
# DecoTengu - dive decompression library.
#
# Copyright (C) 2013-2014 by Artur Wroblewski <wrobell@pld-linux.org>
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

"""Shared type definitions for DecoTengu."""

from dataclasses import dataclass, field
from enum import Enum
from itertools import zip_longest

from . import const


class Phase(str, Enum):
    """Dive phase enumeration."""

    START = "start"
    DESCENT = "descent"
    CONST = "const"
    ASCENT = "ascent"
    DECO_STOP = "deco_stop"
    GAS_SWITCH = "gas_switch"


@dataclass(frozen=True, slots=True)
class Gas:
    """Gas mix configuration.

    Fractions are expressed as percentages (e.g. 21 for 21% O2).

    :param o2: O2 percentage (0-100).
    :param he: Helium percentage (0-100).
    :param h2: Hydrogen percentage (0-100). **EXPERIMENTAL** — see warning below.
    :param n2: Nitrogen percentage (computed as 100 - o2 - he - h2).
    :param switch_depth: Depth at which to switch to this gas [m] (>= 0).
    :param label: Optional label for the gas mix.
    :raises ValueError: If fractions are out of range or sum exceeds 100%.

    .. warning::
        Hydrogen (H2) gas support is **highly experimental**. H2 decompression
        coefficients are derived from diffusion-theory scaling of He half-times
        (factor ≈ √(M_H2/M_He) ≈ 0.71) and use He a/b values as a proxy.
        No validated empirical ZHL-16 H2 coefficient set is publicly available.
        Do **NOT** use H2 calculations for actual dive planning.

    .. note::
        H2 mixes (hydreliox) require O2 ≤ 4% to prevent combustion risk.
        This limit is enforced at construction time.
    """

    o2: float
    he: float = 0.0
    h2: float = 0.0
    switch_depth: float = 0.0
    label: str = ""

    def __post_init__(self) -> None:
        """Validate gas mix fractions."""
        if not (0.0 <= self.o2 <= 100.0):
            raise ValueError(f"O2 must be between 0 and 100, got {self.o2}")
        if not (0.0 <= self.he <= 100.0):
            raise ValueError(f"He must be between 0 and 100, got {self.he}")
        if not (0.0 <= self.h2 <= 100.0):
            raise ValueError(f"H2 must be between 0 and 100, got {self.h2}")
        if self.o2 + self.he + self.h2 > 100.0:
            raise ValueError(
                f"O2 + He + H2 must not exceed 100%, "
                f"got {self.o2} + {self.he} + {self.h2} = {self.o2 + self.he + self.h2}"
            )
        if self.switch_depth < 0.0:
            raise ValueError(f"switch_depth must be >= 0, got {self.switch_depth}")
        if self.h2 > 0.0 and self.o2 > 4.0:
            raise ValueError(
                f"H2 mixes require O2 <= 4% to prevent combustion risk, got O2={self.o2}%. "
                f"Reduce O2 fraction or remove H2."
            )

    @property
    def n2(self) -> float:
        """Nitrogen percentage."""
        return 100.0 - self.o2 - self.he - self.h2

    def __repr__(self) -> str:
        if self.h2 > 0:
            return f"Gas(Hydreliox {self.o2:.0f}/{self.he:.0f}/{self.h2:.0f})"
        elif self.he > 0:
            return f"Gas(Tx {self.o2:.0f}/{self.he:.0f})"
        elif self.o2 == 21:
            return "Gas(Air)"
        else:
            return f"Gas(EAN{self.o2:.0f})"


@dataclass(frozen=True, slots=True)
class Cylinder:
    """Cylinder definition for gas consumption tracking.

    :param volume_litres: Water volume of cylinder in litres (must be > 0).
    :param fill_bar: Fill pressure in bar (must be > 0).
    :raises ValueError: If volume or fill pressure is not positive.
    """

    volume_litres: float
    fill_bar: float

    def __post_init__(self) -> None:
        """Validate cylinder parameters."""
        if self.volume_litres <= 0:
            raise ValueError(f"volume_litres must be positive, got {self.volume_litres}")
        if self.fill_bar <= 0:
            raise ValueError(f"fill_bar must be positive, got {self.fill_bar}")

    @property
    def total_litres(self) -> float:
        """Total gas available at surface pressure."""
        return self.volume_litres * self.fill_bar


@dataclass(frozen=True, slots=True)
class TissueState:
    """Tissue compartment loading state.

    Stores inert gas pressures for all 16 compartments.

    :param n2_pressures: Nitrogen pressure in each compartment [bar].
    :param he_pressures: Helium pressure in each compartment [bar].
    :param h2_pressures: Hydrogen pressure in each compartment [bar].
        Defaults to zero (no hydrogen loading). **EXPERIMENTAL**.
    """

    n2_pressures: tuple[float, ...]
    he_pressures: tuple[float, ...]
    h2_pressures: tuple[float, ...] = field(default_factory=tuple)

    @property
    def total_pressures(self) -> tuple[float, ...]:
        """Combined inert gas pressure in each compartment."""
        return tuple(
            n2 + he + h2
            for n2, he, h2 in zip_longest(
                self.n2_pressures, self.he_pressures, self.h2_pressures, fillvalue=0.0
            )
        )


@dataclass(frozen=True, slots=True)
class DecoStop:
    """Decompression stop information.

    :param depth: Depth of decompression stop [m].
    :param time: Duration of decompression stop [min].
    """

    depth: float
    time: float


@dataclass(frozen=True, slots=True)
class Step:
    """Dive step information.

    :param phase: Current dive phase.
    :param abs_p: Absolute pressure at depth [bar].
    :param time: Cumulative time of dive [min].
    :param gas: Gas mix configuration.
    :param tissues: Tissue compartment state.
    :param gf: Current gradient factor value.
    :param ceiling: Current ascent ceiling pressure [bar].
    :param surface_pressure: Surface atmospheric pressure [bar].
    """

    phase: Phase
    abs_p: float
    time: float
    gas: Gas
    tissues: TissueState
    gf: float
    ceiling: float = 0.0
    surface_pressure: float = const.SURFACE_PRESSURE

    @property
    def depth(self) -> float:
        """Depth in metres."""
        return (self.abs_p - self.surface_pressure) / const.METER_TO_BAR

    def __repr__(self) -> str:
        return (
            f'Step(phase="{self.phase.value}", abs_p={self.abs_p:.4f}, '
            f"time={self.time:.4f}, gf={self.gf:.4f})"
        )


@dataclass(slots=True)
class GasUsage:
    """Gas consumption tracking for a single cylinder.

    :param gas: The gas mix.
    :param cylinder: The cylinder definition.
    :param consumed_litres: Total litres consumed at surface pressure.
    """

    gas: Gas
    cylinder: Cylinder
    consumed_litres: float = 0.0

    @property
    def remaining_litres(self) -> float:
        """Remaining gas in litres at surface pressure."""
        return self.cylinder.total_litres - self.consumed_litres

    @property
    def remaining_bar(self) -> float:
        """Remaining pressure in bar."""
        if self.cylinder.volume_litres == 0:
            return 0.0
        return self.remaining_litres / self.cylinder.volume_litres


@dataclass(frozen=True, slots=True)
class DiveSummary:
    """Summary of a completed dive calculation.

    :param runtime: Total dive runtime [min].
    :param total_deco_time: Total decompression obligation [min].
    :param stops: List of decompression stops.
    :param max_depth: Maximum depth reached [m].
    :param tissues_final: Final tissue state.
    :param cns_percent: CNS oxygen toxicity percentage.
    :param otu: Oxygen toxicity units (UPTD).
    :param ndl: No-decompression limit — additional minutes of bottom time remaining
        before a deco stop would be required [min]. None for deco dives.
    :param gas_usage: Gas consumption by label.
    :param max_gas_density: Maximum gas density encountered during the dive [g/L].
    :param stop_runtimes: Maps stop depth -> cumulative runtime (minutes) at END of that stop.
        e.g. {6.0: 52.0, 3.0: 62.0} means 6m stop ended at T=52min, 3m at T=62min.
    :param profile: (time, depth) waypoints for the full dive: surface start, bottom,
        each stop, surface arrival.
    :param back_gas_ascent_litres: Litres of back gas consumed during ascent from leaving
        bottom to first deco gas switch. Used to calculate min gas / turn pressure.
    :param max_pph2: Maximum hydrogen partial pressure encountered during the dive [bar].
        Only non-zero for dives using H2-containing gases. **EXPERIMENTAL**.
    """

    runtime: float
    total_deco_time: float
    stops: list[DecoStop]
    max_depth: float
    tissues_final: TissueState
    cns_percent: float = 0.0
    otu: float = 0.0
    ndl: float | None = None
    gas_usage: dict[str, GasUsage] = field(default_factory=dict)
    max_gas_density: float = 0.0
    stop_runtimes: dict[float, float] = field(default_factory=dict)
    profile: list[tuple[float, float]] = field(default_factory=list)
    back_gas_ascent_litres: float = 0.0
    ceiling_profile: list[tuple[float, float, float]] = field(default_factory=list)
    # (time_min, diver_depth_m, ceiling_depth_m) — sampled at each profile waypoint
    gas_pressure_profile: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    # gas_label -> [(time_min, bar_remaining), ...]
    max_pph2: float = 0.0
