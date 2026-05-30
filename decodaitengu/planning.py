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

"""High-level dive planning API.

Provides a simple one-call interface for common dive planning tasks,
wrapping the engine configuration and calculation into a single function.

Example::

    from decodaitengu.planning import plan_dive
    from decodaitengu.types import Gas
    from decodaitengu.models import ZHL16C

    result = plan_dive(
        depth=50,
        bottom_time=25,
        back_gas=Gas(21, 35),
        deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
        gf=(30, 85),
    )
    print(result.runtime)
    print(result.stops)
    print(result.cns_percent)
"""



import math

from . import const
from .models import ZHL16C
from .models.base import ZHL16GF
from .tracking.cns import CNSMethod, CNSTracker
from .tracking.otu import OTUTracker
from .types import DecoStop, DiveSummary, Gas


def _depth_to_pressure(depth: float) -> float:
    """Convert depth in metres to absolute pressure in bar."""
    return depth * const.METER_TO_BAR + const.SURFACE_PRESSURE


def _pressure_to_depth(abs_p: float) -> float:
    """Convert absolute pressure to depth in metres."""
    return (abs_p - const.SURFACE_PRESSURE) / const.METER_TO_BAR


def _ceil_to_3m(depth: float) -> float:
    """Round depth up to nearest multiple of 3m."""
    return math.ceil(depth / 3.0) * 3.0


def plan_dive(
    depth: float,
    bottom_time: float,
    back_gas: Gas | None = None,
    deco_gases: list[Gas] | None = None,
    gf: tuple[float, float] = (30, 85),
    descent_rate: float = 20.0,
    ascent_rate: float = 10.0,
    last_stop_depth: float = 3.0,
    model: type[ZHL16GF] | ZHL16GF | None = None,
    surface_pressure: float = const.SURFACE_PRESSURE,
    cns_method: CNSMethod = CNSMethod.EXPONENTIAL,
) -> DiveSummary:
    """Plan a dive and return a complete summary.

    This is the primary high-level API for DecoTengu. It configures the
    decompression model, runs the calculation, and returns all commonly
    needed results in a single call.

    :param depth: Maximum dive depth [m].
    :param bottom_time: Bottom time [min] (from surface to leaving bottom).
    :param back_gas: Back gas mix. Default is Air (21/0).
    :param deco_gases: List of decompression gas mixes with switch depths set.
    :param gf: Gradient factors as (low, high) percentages (e.g. (30, 85)).
    :param descent_rate: Descent rate [m/min]. Default 20.
    :param ascent_rate: Ascent rate [m/min]. Default 10.
    :param last_stop_depth: Depth of last deco stop [m]. Default 3.
    :param model: Decompression model class or instance. Default ZHL16C.
    :param const.SURFACE_PRESSURE: Surface pressure [bar]. Default 1.01325.
    :param cns_method: CNS calculation method. Default EXPONENTIAL.
    :returns: DiveSummary with all dive information.
    """
    if back_gas is None:
        back_gas = Gas(o2=21, he=0)
    if deco_gases is None:
        deco_gases = []

    # Instantiate model
    gf_low = gf[0] / 100.0 if gf[0] > 1.0 else gf[0]
    gf_high = gf[1] / 100.0 if gf[1] > 1.0 else gf[1]

    if model is None:
        deco_model = ZHL16C(gf_low=gf_low, gf_high=gf_high)
    elif isinstance(model, type):
        deco_model = model(gf_low=gf_low, gf_high=gf_high)
    else:
        deco_model = model
        deco_model.gf_low = gf_low
        deco_model.gf_high = gf_high

    # Trackers
    cns_tracker = CNSTracker(method=cns_method)
    otu_tracker = OTUTracker()

    # Initialise tissues
    tissues = deco_model.init(const.SURFACE_PRESSURE)

    # -- DESCENT --
    descent_time = depth / descent_rate
    descent_rate_bar = descent_rate * const.METER_TO_BAR
    tissues = deco_model.load(tissues, const.SURFACE_PRESSURE, descent_time, back_gas, descent_rate_bar)

    # Track O2 exposure during descent (use average depth)
    avg_descent_pressure = const.SURFACE_PRESSURE + (depth * const.METER_TO_BAR / 2.0)
    po2_descent = (back_gas.o2 / 100.0) * avg_descent_pressure
    cns_tracker.update(po2_descent, descent_time)
    otu_tracker.update(po2_descent, descent_time)

    runtime = descent_time

    # -- BOTTOM --
    bottom_duration = bottom_time - descent_time
    if bottom_duration <= 0:
        raise ValueError("Bottom time must be greater than descent time")

    abs_p_bottom = _depth_to_pressure(depth)
    tissues = deco_model.load(tissues, abs_p_bottom, bottom_duration, back_gas, 0.0)

    po2_bottom = (back_gas.o2 / 100.0) * abs_p_bottom
    cns_tracker.update(po2_bottom, bottom_duration)
    otu_tracker.update(po2_bottom, bottom_duration)

    runtime += bottom_duration

    # -- ASCENT with DECO --
    # Sort deco gases by switch depth (deepest first)
    all_gases = [back_gas] + sorted(deco_gases, key=lambda g: g.switch_depth, reverse=True)

    # Find first deco stop
    ascent_rate_bar = ascent_rate * const.METER_TO_BAR
    stops: list[DecoStop] = []
    current_depth = depth
    current_gas = back_gas

    # Determine ceiling
    ceiling_depth = _pressure_to_depth(deco_model.ceiling(tissues, gf_low))
    first_stop_depth = max(last_stop_depth, _ceil_to_3m(ceiling_depth))

    # Check if NDL dive
    # Simulate ascent to surface and check ceiling
    test_ascent_time = current_depth / ascent_rate
    test_tissues = deco_model.load(
        tissues, abs_p_bottom, test_ascent_time, current_gas, -ascent_rate_bar
    )
    surface_ceiling = deco_model.ceiling(test_tissues, gf_high)

    if surface_ceiling <= const.SURFACE_PRESSURE:
        # NDL dive - just ascend
        ascent_time = current_depth / ascent_rate
        avg_ascent_p = abs_p_bottom - (current_depth * const.METER_TO_BAR / 2.0)
        po2_ascent = (current_gas.o2 / 100.0) * avg_ascent_p
        cns_tracker.update(po2_ascent, ascent_time)
        otu_tracker.update(po2_ascent, ascent_time)

        tissues = test_tissues
        runtime += ascent_time

        return DiveSummary(
            runtime=round(runtime, 1),
            total_deco_time=0.0,
            stops=[],
            max_depth=depth,
            tissues_final=tissues,
            cns_percent=round(cns_tracker.cns_percent, 1),
            otu=round(otu_tracker.otu, 1),
            ndl=None,  # TODO: calculate actual NDL
        )

    # Deco dive - ascend to first stop
    # Ascend to first deco stop (or gas switch, whichever is shallower from bottom)
    # Process ascent in stages, handling gas switches
    total_deco_time = 0.0

    # Free ascent to first stop
    ascent_to_first = current_depth - first_stop_depth
    if ascent_to_first > 0:
        free_ascent_time = ascent_to_first / ascent_rate
        tissues = deco_model.load(
            tissues, abs_p_bottom, free_ascent_time, current_gas, -ascent_rate_bar
        )
        avg_p = abs_p_bottom - (ascent_to_first * const.METER_TO_BAR / 2.0)
        po2 = (current_gas.o2 / 100.0) * avg_p
        cns_tracker.update(po2, free_ascent_time)
        otu_tracker.update(po2, free_ascent_time)
        runtime += free_ascent_time
        current_depth = first_stop_depth

    # Calculate number of stops from first stop to surface
    n_stops = int(round((first_stop_depth - last_stop_depth) / 3.0)) + 1
    if n_stops < 1:
        n_stops = 1

    gf_step = (gf_high - gf_low) / n_stops if n_stops > 0 else 0.0
    current_gf = gf_low

    # Process each 3m stop from first_stop_depth down to last_stop_depth
    stop_depth = first_stop_depth
    while stop_depth >= last_stop_depth:
        abs_p_stop = _depth_to_pressure(stop_depth)
        current_gf += gf_step
        current_gf = min(current_gf, gf_high)
        next_gf = current_gf

        # Check for gas switch at this depth
        for g in all_gases[1:]:  # skip back gas
            if g.switch_depth >= stop_depth and g != current_gas:
                current_gas = g
                break

        # Wait at stop until we can ascend to next stop
        stop_time = 0.0
        while True:
            # Check if we can ascend 3m (or to surface for last stop)
            if stop_depth <= last_stop_depth:
                # Last stop - check ascent to surface
                ascent_seg_time = stop_depth / ascent_rate
                test_tissues = deco_model.load(
                    tissues, abs_p_stop, ascent_seg_time, current_gas, -ascent_rate_bar
                )
                test_ceiling = deco_model.ceiling(test_tissues, gf_high)
                if test_ceiling <= const.SURFACE_PRESSURE:
                    break
            else:
                # Check ascent to next stop (3m shallower)
                ascent_seg_time = 3.0 / ascent_rate
                test_tissues = deco_model.load(
                    tissues, abs_p_stop, ascent_seg_time, current_gas, -ascent_rate_bar
                )
                next_stop_p = _depth_to_pressure(stop_depth - 3.0)
                test_ceiling = deco_model.ceiling(test_tissues, next_gf)
                if test_ceiling <= next_stop_p:
                    break

            # Stay 1 more minute
            tissues = deco_model.load(tissues, abs_p_stop, 1.0, current_gas, 0.0)
            po2 = (current_gas.o2 / 100.0) * abs_p_stop
            cns_tracker.update(po2, 1.0)
            otu_tracker.update(po2, 1.0)
            stop_time += 1.0
            runtime += 1.0

        if stop_time > 0:
            stops.append(DecoStop(depth=stop_depth, time=stop_time))
            total_deco_time += stop_time

        # Ascend 3m to next stop (or to surface from last stop)
        if stop_depth <= last_stop_depth:
            ascent_time = stop_depth / ascent_rate
            tissues = deco_model.load(
                tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (stop_depth * const.METER_TO_BAR / 2.0)
        else:
            ascent_time = 3.0 / ascent_rate
            tissues = deco_model.load(
                tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (3.0 * const.METER_TO_BAR / 2.0)

        po2 = (current_gas.o2 / 100.0) * avg_p
        cns_tracker.update(po2, ascent_time)
        otu_tracker.update(po2, ascent_time)
        runtime += ascent_time

        if stop_depth <= last_stop_depth:
            break
        stop_depth -= 3.0

    return DiveSummary(
        runtime=round(runtime, 1),
        total_deco_time=round(total_deco_time, 1),
        stops=stops,
        max_depth=depth,
        tissues_final=tissues,
        cns_percent=round(cns_tracker.cns_percent, 1),
        otu=round(otu_tracker.otu, 1),
        ndl=None,
    )
