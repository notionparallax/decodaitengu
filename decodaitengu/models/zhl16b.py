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

"""ZH-L16B decompression model with gradient factors.

ZH-L16B-GF is the original Bühlmann model variant used for dive table
calculations. Coefficients sourced from Erik Baker's gfdeco.f implementation.

H2 coefficients are **EXPERIMENTAL**: half-times derived by scaling He half-times
by √(M_H2/M_He) ≈ 0.7097 (diffusion theory); a/b values use He coefficients as a
proxy. No validated empirical ZHL-16 H2 coefficient set is publicly available.
These values are for research and estimation only — NOT for dive planning.
"""

from .base import ZHL16GF, ModelParams

# H2 half-times = He half-times × √(M_H2 / M_He) ≈ He × 0.7097
# H2 a/b: He values used as proxy (no published empirical ZHL-16 H2 data).
_H2_SCALE = 0.7097

_ZHL16B_HE_HALF_LIFE = (
    1.88,
    3.02,
    4.72,
    6.99,
    10.21,
    14.48,
    20.53,
    29.11,
    41.20,
    55.19,
    70.69,
    90.34,
    115.29,
    147.42,
    188.24,
    240.03,
)
_ZHL16B_HE_A = (
    1.6189,
    1.3830,
    1.1919,
    1.0458,
    0.9220,
    0.8205,
    0.7305,
    0.6502,
    0.5950,
    0.5545,
    0.5333,
    0.5189,
    0.5181,
    0.5176,
    0.5172,
    0.5119,
)
_ZHL16B_HE_B = (
    0.4770,
    0.5747,
    0.6527,
    0.7223,
    0.7582,
    0.7957,
    0.8279,
    0.8553,
    0.8757,
    0.8903,
    0.8997,
    0.9073,
    0.9122,
    0.9171,
    0.9217,
    0.9267,
)

ZHL16B_PARAMS = ModelParams(
    n2_half_life=(
        5.0,
        8.0,
        12.5,
        18.5,
        27.0,
        38.3,
        54.3,
        77.0,
        109.0,
        146.0,
        187.0,
        239.0,
        305.0,
        390.0,
        498.0,
        635.0,
    ),
    n2_a=(
        1.1696,
        1.0000,
        0.8618,
        0.7562,
        0.6667,
        0.5600,
        0.4947,
        0.4500,
        0.4187,
        0.3798,
        0.3497,
        0.3223,
        0.2850,
        0.2737,
        0.2523,
        0.2327,
    ),
    n2_b=(
        0.5578,
        0.6514,
        0.7222,
        0.7825,
        0.8126,
        0.8434,
        0.8693,
        0.8910,
        0.9092,
        0.9222,
        0.9319,
        0.9403,
        0.9477,
        0.9544,
        0.9602,
        0.9653,
    ),
    he_half_life=_ZHL16B_HE_HALF_LIFE,
    he_a=_ZHL16B_HE_A,
    he_b=_ZHL16B_HE_B,
    h2_half_life=tuple(round(hl * _H2_SCALE, 3) for hl in _ZHL16B_HE_HALF_LIFE),
    h2_a=_ZHL16B_HE_A,
    h2_b=_ZHL16B_HE_B,
)


class ZHL16B(ZHL16GF):
    """ZH-L16B-GF decompression model.

    Used for dive table calculations. This is the legacy model retained
    for backward compatibility. Prefer ZHL16C for new applications.

    Coefficients sourced from Erik Baker's gfdeco.f.
    """

    params = ZHL16B_PARAMS
