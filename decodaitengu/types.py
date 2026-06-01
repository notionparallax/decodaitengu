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

    :param o2: O2 percentage.
    :param he: Helium percentage.
    :param n2: Nitrogen percentage (computed as 100 - o2 - he).
    :param switch_depth: Depth at which to switch to this gas [m].
    :param label: Optional label for the gas mix.
    """

    o2: float
    he: float = 0.0
    switch_depth: float = 0.0
    label: str = ""

    @property
    def n2(self) -> float:
        """Nitrogen percentage."""
        return 100.0 - self.o2 - self.he

    def __repr__(self) -> str:
        if self.he > 0:
            return f"Gas(Tx {self.o2:.0f}/{self.he:.0f})"
        elif self.o2 == 21:
            return "Gas(Air)"
        else:
            return f"Gas(EAN{self.o2:.0f})"


@dataclass(frozen=True, slots=True)
class Cylinder:
    """Cylinder definition for gas consumption tracking.

    :param volume_litres: Water volume of cylinder in litres.
    :param fill_bar: Fill pressure in bar.
    """

    volume_litres: float
    fill_bar: float

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
    """

    n2_pressures: tuple[float, ...]
    he_pressures: tuple[float, ...]

    @property
    def total_pressures(self) -> tuple[float, ...]:
        """Combined inert gas pressure in each compartment."""
        return tuple(n2 + he for n2, he in zip(self.n2_pressures, self.he_pressures, strict=True))


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
    """

    phase: Phase
    abs_p: float
    time: float
    gas: Gas
    tissues: TissueState
    gf: float
    ceiling: float = 0.0

    @property
    def depth(self) -> float:
        """Depth in metres (assumes 0.09985 bar/m and 1.01325 surface)."""
        return (self.abs_p - 1.01325) / 0.09985

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
    :param ndl: No-decompression limit if no deco required [min], else None.
    :param gas_usage: Gas consumption by label.
    :param max_gas_density: Maximum gas density encountered during the dive [g/L].
    :param stop_runtimes: Maps stop depth -> cumulative runtime (minutes) at END of that stop.
        e.g. {6.0: 52.0, 3.0: 62.0} means 6m stop ended at T=52min, 3m at T=62min.
    :param profile: (time, depth) waypoints for the full dive: surface start, bottom,
        each stop, surface arrival.
    :param back_gas_ascent_litres: Litres of back gas consumed during ascent from leaving
        bottom to first deco gas switch. Used to calculate min gas / turn pressure.
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
