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
from .types import Cylinder, DecoStop, DiveSummary, Gas, GasUsage, TissueState


def _depth_to_pressure(depth: float) -> float:
    """Convert depth in metres to absolute pressure in bar."""
    return depth * const.METER_TO_BAR + const.SURFACE_PRESSURE


def _pressure_to_depth(abs_p: float) -> float:
    """Convert absolute pressure to depth in metres."""
    return (abs_p - const.SURFACE_PRESSURE) / const.METER_TO_BAR


def _ceil_to_3m(depth: float) -> float:
    """Round depth up to nearest multiple of 3m."""
    return math.ceil(depth / 3.0) * 3.0


# Molecular weights [g/mol]
_MW_O2 = 31.998
_MW_N2 = 28.014
_MW_HE = 4.003
# Ideal gas constant [L*bar/(mol*K)]
_R = 0.083145
# Body temperature [K] (37 degC) -- standard for dive gas density calculations
_BODY_TEMP_K = 310.15


def _gas_density(gas: Gas, abs_p: float) -> float:
    """Calculate gas density at a given absolute pressure.

    Uses the ideal gas law at body temperature (37 degC / 310.15 K), which is
    the standard reference condition for dive gas density calculations.

    :param gas: Gas mix.
    :param abs_p: Absolute pressure [bar].
    :returns: Gas density [g/L].
    """
    f_o2 = gas.o2 / 100.0
    f_he = gas.he / 100.0
    f_n2 = gas.n2 / 100.0
    mw_mix = f_o2 * _MW_O2 + f_n2 * _MW_N2 + f_he * _MW_HE
    return (mw_mix * abs_p) / (_R * _BODY_TEMP_K)


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
    sac_bottom: float = 20.0,
    sac_deco: float = 17.0,
    back_cylinder: Cylinder | None = None,
    deco_cylinders: list[Cylinder] | None = None,
    descent_stops: list[tuple[float, float]] | None = None,
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
    :param surface_pressure: Surface pressure [bar]. Default 1.01325.
    :param cns_method: CNS calculation method. Default EXPONENTIAL.
    :param sac_bottom: Surface-equivalent SAC [L/min] for descent and bottom. Default 20.
    :param sac_deco: Surface-equivalent SAC [L/min] for deco stops and ascent. Default 17.
    :param back_cylinder: Back gas cylinder. If provided, gas_usage is populated.
    :param deco_cylinders: Deco gas cylinders, parallel to deco_gases list.
    :param descent_stops: Optional list of (depth_m, time_min) stops to make during
        descent (e.g. S-drill at 5m). Stops are sorted by depth and must be shallower
        than the target depth. Tissue loading is computed correctly for each segment.
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
        deco_model: ZHL16GF = ZHL16C(gf_low=gf_low, gf_high=gf_high)
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

    # Gas consumption tracking (only if cylinders provided)
    _gas_consumed: dict[str, float] = {}
    _track_enabled = back_cylinder is not None or deco_cylinders is not None

    def _gas_label(g: Gas) -> str:
        return g.label if g.label else f"Tx{g.o2:.0f}/{g.he:.0f}"

    def _track_gas(g: Gas, duration: float, avg_abs_p: float, sac: float) -> None:
        litres = sac * duration * (avg_abs_p / surface_pressure)
        lbl = _gas_label(g)
        _gas_consumed[lbl] = _gas_consumed.get(lbl, 0.0) + litres

    # Profile and stop runtime tracking
    _profile: list[tuple[float, float]] = [(0.0, 0.0)]
    _stop_runtimes: dict[float, float] = {}
    _ceiling_profile: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    _gas_pressure_profile: dict[str, list[tuple[float, float]]] = {}

    # Build cylinder lookup for gas pressure profile snapshots
    _cylinders_by_label: dict[str, Cylinder] = {}
    if _track_enabled:
        _all_divegases_list = [back_gas] + (deco_gases or [])
        _all_cyls_list = ([back_cylinder] if back_cylinder else []) + (
            deco_cylinders if deco_cylinders else []
        )
        for _dg, _dc in zip(_all_divegases_list, _all_cyls_list, strict=True):
            _cylinders_by_label[_gas_label(_dg)] = _dc
        for _lbl, _cyl in _cylinders_by_label.items():
            _gas_pressure_profile[_lbl] = [(0.0, round(_cyl.fill_bar, 1))]

    def _snapshot_state(t: float, d: float, snap_tissues: TissueState, snap_gf: float) -> None:
        """Record ceiling depth and gas pressures at a profile waypoint."""
        ceiling_p = deco_model.ceiling(snap_tissues, snap_gf)
        ceiling_d = max(0.0, _pressure_to_depth(ceiling_p))
        _ceiling_profile.append((round(t, 2), round(d, 1), round(ceiling_d, 1)))
        if _track_enabled:
            for _lbl, _cyl in _cylinders_by_label.items():
                _consumed = _gas_consumed.get(_lbl, 0.0)
                _remaining = max(0.0, _cyl.fill_bar - _consumed / _cyl.volume_litres)
                _gas_pressure_profile[_lbl].append((round(t, 2), round(_remaining, 1)))

    # -- DESCENT (with optional stops) --
    descent_rate_bar = descent_rate * const.METER_TO_BAR

    # Build ordered list of descent waypoints: (depth, stop_time)
    # Sort shallower-first so we descend through them in order
    _descent_stops: list[tuple[float, float]] = []
    if descent_stops:
        _descent_stops = sorted(
            [(float(d), float(t)) for d, t in descent_stops if 0 < d < depth],
            key=lambda x: x[0],
        )

    _prev_depth = 0.0
    descent_time = 0.0
    runtime = 0.0
    for stop_depth, stop_time in _descent_stops:
        seg_time = (stop_depth - _prev_depth) / descent_rate
        seg_start_p = _depth_to_pressure(_prev_depth)
        tissues = deco_model.load(tissues, seg_start_p, seg_time, back_gas, descent_rate_bar)
        avg_seg_p = (_depth_to_pressure(_prev_depth) + _depth_to_pressure(stop_depth)) / 2.0
        po2_seg = (back_gas.o2 / 100.0) * avg_seg_p
        cns_tracker.update(po2_seg, seg_time)
        otu_tracker.update(po2_seg, seg_time)
        if _track_enabled:
            _track_gas(back_gas, seg_time, avg_seg_p, sac_bottom)
        runtime += seg_time
        descent_time += seg_time
        # Arrival waypoint: start of stop — gives the chart a flat horizontal stop segment
        _snapshot_state(runtime, stop_depth, tissues, gf_low)
        _profile.append((round(runtime, 2), stop_depth))

        # Stop at this depth
        stop_p = _depth_to_pressure(stop_depth)
        po2_stop = (back_gas.o2 / 100.0) * stop_p
        tissues = deco_model.load(tissues, stop_p, stop_time, back_gas, 0.0)
        cns_tracker.update(po2_stop, stop_time)
        otu_tracker.update(po2_stop, stop_time)
        if _track_enabled:
            _track_gas(back_gas, stop_time, stop_p, sac_bottom)
        runtime += stop_time
        descent_time += stop_time
        _snapshot_state(runtime, stop_depth, tissues, gf_low)
        _profile.append((round(runtime, 2), stop_depth))
        _prev_depth = stop_depth

    # Final descent segment from last waypoint to target depth
    final_seg_time = (depth - _prev_depth) / descent_rate
    seg_start_p = _depth_to_pressure(_prev_depth)
    tissues = deco_model.load(tissues, seg_start_p, final_seg_time, back_gas, descent_rate_bar)
    avg_descent_pressure = (_depth_to_pressure(_prev_depth) + _depth_to_pressure(depth)) / 2.0
    po2_descent = (back_gas.o2 / 100.0) * avg_descent_pressure
    cns_tracker.update(po2_descent, final_seg_time)
    otu_tracker.update(po2_descent, final_seg_time)
    if _track_enabled:
        _track_gas(back_gas, final_seg_time, avg_descent_pressure, sac_bottom)
    runtime += final_seg_time
    descent_time += final_seg_time
    _snapshot_state(runtime, depth, tissues, gf_low)
    _profile.append((round(runtime, 2), depth))

    # -- BOTTOM --
    bottom_duration = bottom_time - descent_time
    if bottom_duration <= 0:
        raise ValueError("Bottom time must be greater than descent time")

    abs_p_bottom = _depth_to_pressure(depth)
    po2_bottom = (back_gas.o2 / 100.0) * abs_p_bottom

    # Process in 1-min steps so the ceiling profile captures growth through bottom time
    remaining_bottom = bottom_duration
    while remaining_bottom > 0:
        step = min(1.0, remaining_bottom)
        tissues = deco_model.load(tissues, abs_p_bottom, step, back_gas, 0.0)
        cns_tracker.update(po2_bottom, step)
        otu_tracker.update(po2_bottom, step)
        if _track_enabled:
            _track_gas(back_gas, step, abs_p_bottom, sac_bottom)
        runtime += step
        remaining_bottom -= step
        _snapshot_state(runtime, depth, tissues, gf_low)

    _profile.append((round(runtime, 2), depth))

    # Max gas density starts at max depth on back gas
    max_gas_density = _gas_density(back_gas, abs_p_bottom)

    # -- ASCENT with DECO --
    all_gases = [back_gas] + sorted(deco_gases, key=lambda g: g.switch_depth, reverse=True)
    ascent_rate_bar = ascent_rate * const.METER_TO_BAR
    stops: list[DecoStop] = []
    current_depth = depth
    current_gas = back_gas

    # Determine ceiling
    ceiling_depth = _pressure_to_depth(deco_model.ceiling(tissues, gf_low))
    first_stop_depth = max(last_stop_depth, _ceil_to_3m(ceiling_depth))

    # Check if NDL dive
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

        if _track_enabled:
            _track_gas(current_gas, ascent_time, avg_ascent_p, sac_deco)

        tissues = test_tissues
        runtime += ascent_time
        _snapshot_state(runtime, 0.0, tissues, gf_high)
        _profile.append((round(runtime, 2), 0.0))

        return DiveSummary(
            runtime=round(runtime, 1),
            total_deco_time=0.0,
            stops=[],
            max_depth=depth,
            tissues_final=tissues,
            cns_percent=round(cns_tracker.cns_percent, 1),
            otu=round(otu_tracker.otu, 1),
            ndl=None,
            max_gas_density=round(max_gas_density, 3),
            stop_runtimes={},
            profile=_profile,
            back_gas_ascent_litres=0.0,
            ceiling_profile=_ceiling_profile,
            gas_pressure_profile=_gas_pressure_profile,
        )

    # Deco dive - ascend to first stop
    total_deco_time = 0.0

    # Free ascent to first stop
    ascent_to_first = current_depth - first_stop_depth
    _back_gas_ascent_litres = 0.0
    _on_back_gas = True
    if ascent_to_first > 0:
        free_ascent_time = ascent_to_first / ascent_rate
        tissues = deco_model.load(
            tissues, abs_p_bottom, free_ascent_time, current_gas, -ascent_rate_bar
        )
        avg_p = abs_p_bottom - (ascent_to_first * const.METER_TO_BAR / 2.0)
        po2 = (current_gas.o2 / 100.0) * avg_p
        cns_tracker.update(po2, free_ascent_time)
        otu_tracker.update(po2, free_ascent_time)
        if _track_enabled:
            _track_gas(current_gas, free_ascent_time, avg_p, sac_deco)
        # Include free ascent in back_gas_ascent_litres (stressed rate)
        _back_gas_ascent_litres += sac_bottom * free_ascent_time * (avg_p / surface_pressure)
        runtime += free_ascent_time
        current_depth = first_stop_depth
    _snapshot_state(runtime, first_stop_depth, tissues, gf_low)
    _profile.append((round(runtime, 2), first_stop_depth))

    # Process each 3m stop from first_stop_depth down to last_stop_depth.
    # GF is interpolated linearly with depth: gf_low at first_stop_depth,
    # gf_high at the surface (depth=0). This is the standard Baker GF definition.
    stop_depth = first_stop_depth
    while stop_depth >= last_stop_depth:
        abs_p_stop = _depth_to_pressure(stop_depth)
        if first_stop_depth > 0:
            current_gf = (
                gf_low + (gf_high - gf_low) * (first_stop_depth - stop_depth) / first_stop_depth
            )
        else:
            current_gf = gf_high
        current_gf = min(current_gf, gf_high)
        # GF for the NEXT stop (3m shallower) — used in the ascent check
        next_stop_depth = stop_depth - 3.0
        if first_stop_depth > 0 and next_stop_depth > 0:
            next_gf = (
                gf_low
                + (gf_high - gf_low) * (first_stop_depth - next_stop_depth) / first_stop_depth
            )
        else:
            next_gf = gf_high
        next_gf = min(next_gf, gf_high)

        # Check for gas switch at this depth — pick the richest (highest O2)
        # eligible gas whose switch_depth allows use at this stop.
        best_gas = current_gas
        for g in all_gases[1:]:  # skip back gas
            if g.switch_depth >= stop_depth and g.o2 > best_gas.o2:
                best_gas = g
        if best_gas != current_gas:
            current_gas = best_gas

        # Detect back gas -> deco gas switch for ascent tracking
        if current_gas != back_gas and _on_back_gas:
            _on_back_gas = False

        # Track density for the current gas at this stop depth
        max_gas_density = max(max_gas_density, _gas_density(current_gas, abs_p_stop))

        # Wait at stop until we can ascend to next stop
        stop_time = 0.0
        while True:
            # Check if we can ascend 3m (or to surface for last stop)
            if stop_depth <= last_stop_depth:
                ascent_seg_time = stop_depth / ascent_rate
                test_tissues = deco_model.load(
                    tissues, abs_p_stop, ascent_seg_time, current_gas, -ascent_rate_bar
                )
                test_ceiling = deco_model.ceiling(test_tissues, gf_high)
                if test_ceiling <= const.SURFACE_PRESSURE:
                    break
            else:
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
            if _track_enabled:
                _track_gas(current_gas, 1.0, abs_p_stop, sac_deco)
            if _on_back_gas:
                _back_gas_ascent_litres += sac_bottom * 1.0 * (abs_p_stop / surface_pressure)
            stop_time += 1.0
            runtime += 1.0

        if stop_time > 0:
            stops.append(DecoStop(depth=stop_depth, time=stop_time))
            total_deco_time += stop_time
            _stop_runtimes[stop_depth] = round(runtime, 2)
        _snapshot_state(runtime, stop_depth, tissues, current_gf)
        _profile.append((round(runtime, 2), stop_depth))

        # Ascend 3m to next stop (or to surface from last stop)
        if stop_depth <= last_stop_depth:
            ascent_time = stop_depth / ascent_rate
            tissues = deco_model.load(
                tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (stop_depth * const.METER_TO_BAR / 2.0)
            next_profile_depth = 0.0
        else:
            ascent_time = 3.0 / ascent_rate
            tissues = deco_model.load(
                tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (3.0 * const.METER_TO_BAR / 2.0)
            next_profile_depth = stop_depth - 3.0

        po2 = (current_gas.o2 / 100.0) * avg_p
        cns_tracker.update(po2, ascent_time)
        otu_tracker.update(po2, ascent_time)
        if _track_enabled:
            _track_gas(current_gas, ascent_time, avg_p, sac_deco)
        if _on_back_gas:
            _back_gas_ascent_litres += sac_bottom * ascent_time * (avg_p / surface_pressure)
        runtime += ascent_time
        _snapshot_state(runtime, next_profile_depth, tissues, next_gf)
        _profile.append((round(runtime, 2), next_profile_depth))

        if stop_depth <= last_stop_depth:
            break
        stop_depth -= 3.0

    # Build gas_usage from tracked consumption
    _gas_usage: dict[str, GasUsage] = {}
    if _track_enabled:
        all_divegases = [back_gas] + (deco_gases or [])
        all_cylinders_list = ([back_cylinder] if back_cylinder else []) + (
            deco_cylinders if deco_cylinders else []
        )
        for i, g in enumerate(all_divegases):
            lbl = _gas_label(g)
            cyl = all_cylinders_list[i] if i < len(all_cylinders_list) else None
            consumed = _gas_consumed.get(lbl, 0.0)
            if cyl is not None:
                _gas_usage[lbl] = GasUsage(gas=g, cylinder=cyl, consumed_litres=consumed)

    return DiveSummary(
        runtime=round(runtime, 1),
        total_deco_time=round(total_deco_time, 1),
        stops=stops,
        max_depth=depth,
        tissues_final=tissues,
        cns_percent=round(cns_tracker.cns_percent, 1),
        otu=round(otu_tracker.otu, 1),
        ndl=None,
        gas_usage=_gas_usage,
        max_gas_density=round(max_gas_density, 3),
        stop_runtimes=_stop_runtimes,
        profile=_profile,
        back_gas_ascent_litres=round(_back_gas_ascent_litres, 2),
        ceiling_profile=_ceiling_profile,
        gas_pressure_profile=_gas_pressure_profile,
    )
