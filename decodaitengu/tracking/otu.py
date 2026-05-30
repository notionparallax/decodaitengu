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

"""OTU (Oxygen Toxicity Unit) / UPTD tracking.

Formula:
    OTU = t * ((PO2 - 0.5) / 0.5) ^ 0.83

for PO2 > 0.5 bar.
"""


class OTUTracker:
    """Tracks OTU (UPTD) accumulation across a dive."""

    def __init__(self) -> None:
        self.otu: float = 0.0

    def reset(self) -> None:
        """Reset OTU tracking to zero."""
        self.otu = 0.0

    def update(self, po2: float, time: float) -> None:
        """Update OTU accumulation for a segment of exposure.

        :param po2: Partial pressure of oxygen during segment [bar].
        :param time: Duration of segment [min].
        """
        if po2 <= 0.5 or time <= 0:
            return
        self.otu += time * ((po2 - 0.5) / 0.5) ** 0.83
