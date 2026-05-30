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

"""ZH-L16C decompression model with gradient factors.

ZH-L16C-GF is the model variant used for real-time dive computer calculations.
More conservative than ZH-L16B. This is the recommended default model.

N2 coefficients sourced from Bühlmann (1990) / OSTC firmware.
He coefficients sourced from Bühlmann (1990) "Tauchmedizin".
"""

from .base import ZHL16GF, ModelParams

ZHL16C_PARAMS = ModelParams(
    n2_half_life=(
        4.0,
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
        1.2599,
        1.0000,
        0.8618,
        0.7562,
        0.6200,
        0.5043,
        0.4410,
        0.4000,
        0.3750,
        0.3500,
        0.3295,
        0.3065,
        0.2835,
        0.2610,
        0.2480,
        0.2327,
    ),
    n2_b=(
        0.5050,
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
    he_half_life=(
        1.51,
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
    ),
    he_a=(
        1.7474,
        1.3838,
        1.1925,
        1.0465,
        0.9226,
        0.8211,
        0.7309,
        0.6514,
        0.5944,
        0.5434,
        0.5002,
        0.4609,
        0.4256,
        0.3957,
        0.3699,
        0.3497,
    ),
    he_b=(
        0.4245,
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
    ),
)


class ZHL16C(ZHL16GF):
    """ZH-L16C-GF decompression model.

    Used for real-time dive computer calculations. More conservative than
    ZH-L16B, particularly in the fast compartments. This is the recommended
    default model for new applications.

    N2 coefficients: Bühlmann (1990) / OSTC firmware.
    He coefficients: Bühlmann (1990) "Tauchmedizin".
    """

    params = ZHL16C_PARAMS
