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

"""Gas consumption tracking.

Calculates gas usage based on SAC rate, depth (ambient pressure), and time.
Gas consumption at depth: litres = SAC * time * (abs_pressure / surface_pressure)
"""

from ..types import Cylinder, Gas, GasUsage


class GasTracker:
    """Tracks gas consumption across a dive.

    :param surface_pressure: Surface pressure [bar]. Default 1.01325.
    :param sac_bottom: SAC rate for bottom phase [L/min at surface]. Default 20.
    :param sac_deco: SAC rate for deco/ascent phases [L/min at surface]. Default 17.
    """

    def __init__(
        self,
        surface_pressure: float = 1.01325,
        sac_bottom: float = 20.0,
        sac_deco: float = 17.0,
    ) -> None:
        self.surface_pressure = surface_pressure
        self.sac_bottom = sac_bottom
        self.sac_deco = sac_deco
        self._usage: dict[str, GasUsage] = {}

    def add_cylinder(self, label: str, gas: Gas, cylinder: Cylinder) -> None:
        """Register a cylinder for gas tracking.

        :param label: Unique label for this cylinder.
        :param gas: Gas mix in this cylinder.
        :param cylinder: Cylinder volume and fill specifications.
        """
        self._usage[label] = GasUsage(gas=gas, cylinder=cylinder)

    def update(
        self,
        label: str,
        abs_p: float,
        time: float,
        is_deco: bool = False,
    ) -> None:
        """Update gas consumption for a segment.

        :param label: Cylinder label being breathed.
        :param abs_p: Average absolute pressure during segment [bar].
        :param time: Duration of segment [min].
        :param is_deco: True if deco/ascent SAC rate should be used.
        """
        if label not in self._usage or time <= 0:
            return

        sac = self.sac_deco if is_deco else self.sac_bottom
        # Gas consumption at depth = SAC * time * (depth_pressure / surface_pressure)
        litres = sac * time * (abs_p / self.surface_pressure)
        self._usage[label].consumed_litres += litres

    @property
    def usage(self) -> dict[str, GasUsage]:
        """Current gas usage state."""
        return dict(self._usage)

    def reset(self) -> None:
        """Reset all consumption to zero."""
        for gu in self._usage.values():
            gu.consumed_litres = 0.0
