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

"""Base decompression model interface and shared calculations.

Implements the ZH-L16-GF decompression model framework with gradient factors
by Erik Baker. Subclasses provide specific coefficient tables (ZHL-16B, ZHL-16C).

Equations
---------
Schreiner Equation (tissue gas loading):
    P = P_alv + R * (t - 1/k) - (P_alv - P_i - R/k) * e^(-k*t)

Bühlmann Equation with gradient factors (ascent ceiling):
    P_l = (P - A * gf) / (gf / B + 1.0 - gf)

For trimix (combined N2 + He):
    A = (A_n2 * P_n2 + A_he * P_he) / (P_n2 + P_he)
    B = (B_n2 * P_n2 + B_he * P_he) / (P_n2 + P_he)
    P_ceiling = (P_n2 + P_he - A * gf) / (gf / B + 1 - gf)
"""

import math
from dataclasses import dataclass
from typing import Protocol

from .. import const
from ..types import Gas, TissueState


@dataclass(frozen=True, slots=True)
class ModelParams:
    """Coefficient table for a ZH-L16 variant.

    :param n2_half_life: N2 half-life times for 16 compartments [min].
    :param n2_a: N2 Bühlmann 'a' coefficients.
    :param n2_b: N2 Bühlmann 'b' coefficients.
    :param he_half_life: He half-life times for 16 compartments [min].
    :param he_a: He Bühlmann 'a' coefficients.
    :param he_b: He Bühlmann 'b' coefficients.
    :param h2_half_life: H2 half-life times for 16 compartments [min]. **EXPERIMENTAL**.
        Derived by scaling He half-times by √(M_H2/M_He) ≈ 0.7097.
        No validated empirical values exist — use for research only.
    :param h2_a: H2 Bühlmann 'a' coefficients. **EXPERIMENTAL** (uses He values as proxy).
    :param h2_b: H2 Bühlmann 'b' coefficients. **EXPERIMENTAL** (uses He values as proxy).
    """

    n2_half_life: tuple[float, ...]
    n2_a: tuple[float, ...]
    n2_b: tuple[float, ...]
    he_half_life: tuple[float, ...]
    he_a: tuple[float, ...]
    he_b: tuple[float, ...]
    h2_half_life: tuple[float, ...]
    h2_a: tuple[float, ...]
    h2_b: tuple[float, ...]


class DecoModel(Protocol):
    """Protocol defining the decompression model interface."""

    params: ModelParams
    gf_low: float
    gf_high: float

    def init(self, surface_pressure: float) -> TissueState: ...
    def load(
        self,
        tissues: TissueState,
        abs_p: float,
        time: float,
        gas: Gas,
        rate: float,
    ) -> TissueState: ...
    def ceiling(self, tissues: TissueState, gf: float) -> float: ...
    def compartment_ceilings(self, tissues: TissueState, gf: float) -> tuple[float, ...]: ...


def eq_schreiner(
    p_i: float,
    p_alv: float,
    rate: float,
    time: float,
    k: float,
) -> float:
    """Calculate inert gas pressure in a tissue compartment using Schreiner equation.

    :param p_i: Initial inert gas pressure in tissue compartment [bar].
    :param p_alv: Alveolar pressure of inspired inert gas [bar].
    :param rate: Rate of change of inert gas pressure [bar/min].
    :param time: Time of exposure [min].
    :param k: Gas decay constant (ln2 / half_life).
    :returns: Final inert gas pressure in tissue compartment [bar].
    """
    return p_alv + rate * (time - 1.0 / k) - (p_alv - p_i - rate / k) * math.exp(-k * time)


def eq_gf_limit(
    gf: float,
    p_n2: float,
    p_he: float,
    a_n2: float,
    b_n2: float,
    a_he: float,
    b_he: float,
    p_h2: float = 0.0,
    a_h2: float = 0.0,
    b_h2: float = 0.0,
) -> float:
    """Calculate ascent ceiling of a tissue compartment.

    Uses Bühlmann equation extended with gradient factors by Erik Baker,
    with the weighted a/b approach for combined N2 + He + H2 loading.

    :param gf: Gradient factor value (0 < gf <= 1.5).
    :param p_n2: Current tissue nitrogen pressure [bar].
    :param p_he: Current tissue helium pressure [bar].
    :param a_n2: Bühlmann 'a' coefficient for nitrogen.
    :param b_n2: Bühlmann 'b' coefficient for nitrogen.
    :param a_he: Bühlmann 'a' coefficient for helium.
    :param b_he: Bühlmann 'b' coefficient for helium.
    :param p_h2: Current tissue hydrogen pressure [bar]. **EXPERIMENTAL**. Default 0.
    :param a_h2: Bühlmann 'a' coefficient for hydrogen. **EXPERIMENTAL**. Default 0.
    :param b_h2: Bühlmann 'b' coefficient for hydrogen. **EXPERIMENTAL**. Default 0.
    :returns: Absolute pressure of ascent ceiling [bar].
    """
    p = p_n2 + p_he + p_h2
    if p <= 0:
        return 0.0
    a = (a_n2 * p_n2 + a_he * p_he + a_h2 * p_h2) / p
    b = (b_n2 * p_n2 + b_he * p_he + b_h2 * p_h2) / p
    return (p - a * gf) / (gf / b + 1.0 - gf)


class ZHL16GF:
    """Base implementation of Bühlmann ZH-L16 with gradient factors.

    Subclasses must set the `params` class variable with appropriate coefficients.

    :param gf_low: Gradient factor low (controls first stop depth). Default 0.30.
    :param gf_high: Gradient factor high (controls last stop duration). Default 0.85.
    """

    params: ModelParams  # Must be set by subclass

    def __init__(self, gf_low: float = 0.30, gf_high: float = 0.85) -> None:
        self.gf_low = gf_low
        self.gf_high = gf_high
        self._n2_k = tuple(const.LOG_2 / hl for hl in self.params.n2_half_life)
        self._he_k = tuple(const.LOG_2 / hl for hl in self.params.he_half_life)
        self._h2_k = tuple(const.LOG_2 / hl for hl in self.params.h2_half_life)

    def init(self, surface_pressure: float) -> TissueState:
        """Initialise tissue compartments for surface saturation.

        :param surface_pressure: Ambient pressure at surface [bar].
        :returns: Initial tissue state with all compartments at surface equilibrium.
        """
        # Standard air composition: 79.02% N2
        p_n2 = 0.7902 * (surface_pressure - const.WATER_VAPOUR_PRESSURE_DEFAULT)
        return TissueState(
            n2_pressures=tuple([p_n2] * 16),
            he_pressures=tuple([0.0] * 16),
            h2_pressures=tuple([0.0] * 16),
        )

    def load(
        self,
        tissues: TissueState,
        abs_p: float,
        time: float,
        gas: Gas,
        rate: float,
    ) -> TissueState:
        """Calculate tissue gas loading for all compartments.

        Applies the Schreiner equation to each compartment for both N2 and He.

        :param tissues: Current tissue state.
        :param abs_p: Absolute pressure at current depth [bar].
        :param time: Time of exposure [min].
        :param gas: Gas mix being breathed.
        :param rate: Pressure rate change [bar/min] (+descent, -ascent, 0=const).
        :returns: Updated tissue state after exposure.
        """
        f_n2 = gas.n2 / 100.0
        f_he = gas.he / 100.0
        f_h2 = gas.h2 / 100.0
        p_alv_n2 = f_n2 * (abs_p - const.WATER_VAPOUR_PRESSURE_DEFAULT)
        p_alv_he = f_he * (abs_p - const.WATER_VAPOUR_PRESSURE_DEFAULT)
        p_alv_h2 = f_h2 * (abs_p - const.WATER_VAPOUR_PRESSURE_DEFAULT)
        r_n2 = f_n2 * rate
        r_he = f_he * rate
        r_h2 = f_h2 * rate

        new_n2 = []
        new_he = []
        new_h2 = []
        for i in range(16):
            new_n2.append(
                eq_schreiner(tissues.n2_pressures[i], p_alv_n2, r_n2, time, self._n2_k[i])
            )
            new_he.append(
                eq_schreiner(tissues.he_pressures[i], p_alv_he, r_he, time, self._he_k[i])
            )
            new_h2.append(
                eq_schreiner(tissues.h2_pressures[i], p_alv_h2, r_h2, time, self._h2_k[i])
            )
        return TissueState(
            n2_pressures=tuple(new_n2),
            he_pressures=tuple(new_he),
            h2_pressures=tuple(new_h2),
        )

    def ceiling(self, tissues: TissueState, gf: float) -> float:
        """Calculate the overall ascent ceiling pressure.

        Returns the maximum (shallowest limit) across all compartments.

        :param tissues: Current tissue state.
        :param gf: Gradient factor to use.
        :returns: Absolute pressure of ascent ceiling [bar].
        """
        return max(self.compartment_ceilings(tissues, gf))

    def compartment_ceilings(self, tissues: TissueState, gf: float) -> tuple[float, ...]:
        """Calculate ascent ceiling for each tissue compartment.

        :param tissues: Current tissue state.
        :param gf: Gradient factor to use.
        :returns: Tuple of ceiling pressures for each compartment.
        """
        params = self.params
        return tuple(
            eq_gf_limit(
                gf,
                tissues.n2_pressures[i],
                tissues.he_pressures[i],
                params.n2_a[i],
                params.n2_b[i],
                params.he_a[i],
                params.he_b[i],
                tissues.h2_pressures[i],
                params.h2_a[i],
                params.h2_b[i],
            )
            for i in range(16)
        )
