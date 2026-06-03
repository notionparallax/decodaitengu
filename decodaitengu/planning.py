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
from dataclasses import dataclass, field

from . import const
from .models import ZHL16C
from .models.base import ZHL16GF
from .tracking.cns import CNSMethod, CNSTracker
from .tracking.otu import OTUTracker
from .types import Cylinder, DecoStop, DiveSummary, Gas, GasUsage, TissueState


def _depth_to_pressure(depth: float, surface_pressure: float) -> float:
    """Convert depth in metres to absolute pressure in bar."""
    return depth * const.METER_TO_BAR + surface_pressure


def _pressure_to_depth(abs_p: float, surface_pressure: float) -> float:
    """Convert absolute pressure to depth in metres."""
    return (abs_p - surface_pressure) / const.METER_TO_BAR


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


def _gas_label(g: Gas) -> str:
    """Return a human-readable label for a gas mix."""
    return g.label if g.label else f"Tx{g.o2:.0f}/{g.he:.0f}"


@dataclass
class _DiveState:
    """Mutable state threaded through dive phases."""

    tissues: TissueState
    runtime: float = 0.0
    cns_tracker: CNSTracker = field(default_factory=CNSTracker)
    otu_tracker: OTUTracker = field(default_factory=OTUTracker)
    gas_consumed: dict[str, float] = field(default_factory=dict)
    profile: list[tuple[float, float]] = field(default_factory=lambda: [(0.0, 0.0)])
    ceiling_profile: list[tuple[float, float, float]] = field(
        default_factory=lambda: [(0.0, 0.0, 0.0)]
    )
    gas_pressure_profile: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    cylinders_by_label: dict[str, Cylinder] = field(default_factory=dict)
    track_enabled: bool = False
    surface_pressure: float = const.SURFACE_PRESSURE
    max_gas_density: float = 0.0

    def track_gas(self, g: Gas, duration: float, avg_abs_p: float, sac: float) -> None:
        """Record gas consumed during a segment."""
        litres = sac * duration * (avg_abs_p / self.surface_pressure)
        lbl = _gas_label(g)
        self.gas_consumed[lbl] = self.gas_consumed.get(lbl, 0.0) + litres

    def snapshot(self, model: ZHL16GF, depth: float, gf: float) -> None:
        """Record ceiling and gas pressures at the current runtime."""
        ceiling_p = model.ceiling(self.tissues, gf)
        ceiling_d = max(0.0, _pressure_to_depth(ceiling_p, self.surface_pressure))
        self.ceiling_profile.append((round(self.runtime, 2), round(depth, 1), round(ceiling_d, 1)))
        if self.track_enabled:
            for lbl, cyl in self.cylinders_by_label.items():
                consumed = self.gas_consumed.get(lbl, 0.0)
                remaining = max(0.0, cyl.fill_bar - consumed / cyl.volume_litres)
                self.gas_pressure_profile[lbl].append(
                    (round(self.runtime, 2), round(remaining, 1))
                )


def _validate_inputs(
    depth: float,
    bottom_time: float,
    descent_rate: float,
    ascent_rate: float,
    last_stop_depth: float,
    sac_bottom: float,
    sac_deco: float,
    gf: tuple[float, float],
    deco_gases: list[Gas],
    surface_pressure: float,
    max_po2: float,
) -> tuple[float, float]:
    """Validate all plan_dive inputs and return (gf_low, gf_high) as fractions.

    :raises ValueError: If any input is invalid.
    """
    if not math.isfinite(depth) or depth <= 0:
        raise ValueError(f"depth must be a positive finite number, got {depth}")
    if not math.isfinite(bottom_time) or bottom_time <= 0:
        raise ValueError(f"bottom_time must be a positive finite number, got {bottom_time}")
    if not math.isfinite(descent_rate) or descent_rate <= 0:
        raise ValueError(f"descent_rate must be a positive finite number, got {descent_rate}")
    if not math.isfinite(ascent_rate) or ascent_rate <= 0:
        raise ValueError(f"ascent_rate must be a positive finite number, got {ascent_rate}")
    if not math.isfinite(last_stop_depth) or last_stop_depth <= 0:
        raise ValueError(
            f"last_stop_depth must be a positive finite number, got {last_stop_depth}"
        )
    if not math.isfinite(sac_bottom) or sac_bottom <= 0:
        raise ValueError(f"sac_bottom must be a positive finite number, got {sac_bottom}")
    if not math.isfinite(sac_deco) or sac_deco <= 0:
        raise ValueError(f"sac_deco must be a positive finite number, got {sac_deco}")

    # GF validation — accepted as percentages (0-100] where gf_low <= gf_high
    gf_low_pct, gf_high_pct = gf
    if not (0 < gf_low_pct <= 100):
        raise ValueError(f"gf_low must be in (0, 100], got {gf_low_pct}")
    if not (0 < gf_high_pct <= 100):
        raise ValueError(f"gf_high must be in (0, 100], got {gf_high_pct}")
    if gf_low_pct > gf_high_pct:
        raise ValueError(f"gf_low must be <= gf_high, got ({gf_low_pct}, {gf_high_pct})")

    # Validate deco gas switch depths
    for i, g in enumerate(deco_gases):
        if g.switch_depth <= 0:
            raise ValueError(f"deco_gases[{i}] ({g}) must have a positive switch_depth")
        if g.switch_depth >= depth:
            raise ValueError(
                f"deco_gases[{i}] switch_depth ({g.switch_depth}m) must be less than "
                f"dive depth ({depth}m)"
            )
        # Validate PO2 at switch depth (0.01 bar tolerance for floating-point)
        abs_p_at_switch = g.switch_depth * const.METER_TO_BAR + surface_pressure
        po2_at_switch = (g.o2 / 100.0) * abs_p_at_switch
        if po2_at_switch > max_po2 + 0.01:
            raise ValueError(
                f"deco_gases[{i}] ({g}) has PO2 {po2_at_switch:.2f} bar at switch depth "
                f"{g.switch_depth}m, which exceeds max_po2={max_po2} bar"
            )

    # Validate surface pressure (reasonable range for altitude diving)
    if not math.isfinite(surface_pressure) or surface_pressure <= 0:
        raise ValueError(
            f"surface_pressure must be a positive finite number, got {surface_pressure}"
        )
    if surface_pressure < 0.5 or surface_pressure > 1.1:
        raise ValueError(
            f"surface_pressure must be between 0.5 and 1.1 bar, got {surface_pressure}. "
            f"(0.5 bar ≈ 5500m altitude, 1.1 bar is above sea level)"
        )

    return gf_low_pct / 100.0, gf_high_pct / 100.0


def _resolve_model(
    model: type[ZHL16GF] | ZHL16GF | None, gf_low: float, gf_high: float
) -> ZHL16GF:
    """Instantiate or configure the decompression model."""
    if model is None:
        return ZHL16C(gf_low=gf_low, gf_high=gf_high)
    elif isinstance(model, type):
        return model(gf_low=gf_low, gf_high=gf_high)
    else:
        model.gf_low = gf_low
        model.gf_high = gf_high
        return model


def _descend(
    state: _DiveState,
    model: ZHL16GF,
    depth: float,
    descent_rate: float,
    back_gas: Gas,
    sac_bottom: float,
    descent_stops: list[tuple[float, float]] | None,
) -> float:
    """Execute the descent phase. Returns total descent time.

    Modifies state in place (tissues, trackers, profile, gas consumption).
    """
    descent_rate_bar = descent_rate * const.METER_TO_BAR

    # Build ordered list of descent waypoints
    ordered_stops: list[tuple[float, float]] = []
    if descent_stops:
        ordered_stops = sorted(
            [(float(d), float(t)) for d, t in descent_stops if 0 < d < depth],
            key=lambda x: x[0],
        )

    prev_depth = 0.0
    descent_time = 0.0

    for stop_depth, stop_time in ordered_stops:
        seg_time = (stop_depth - prev_depth) / descent_rate
        seg_start_p = _depth_to_pressure(prev_depth, state.surface_pressure)
        state.tissues = model.load(
            state.tissues, seg_start_p, seg_time, back_gas, descent_rate_bar
        )
        avg_seg_p = (
            _depth_to_pressure(prev_depth, state.surface_pressure)
            + _depth_to_pressure(stop_depth, state.surface_pressure)
        ) / 2.0
        po2_seg = (back_gas.o2 / 100.0) * avg_seg_p
        state.cns_tracker.update(po2_seg, seg_time)
        state.otu_tracker.update(po2_seg, seg_time)
        if state.track_enabled:
            state.track_gas(back_gas, seg_time, avg_seg_p, sac_bottom)
        state.runtime += seg_time
        descent_time += seg_time
        state.snapshot(model, stop_depth, model.gf_low)
        state.profile.append((round(state.runtime, 2), stop_depth))

        # Stop at this depth
        stop_p = _depth_to_pressure(stop_depth, state.surface_pressure)
        po2_stop = (back_gas.o2 / 100.0) * stop_p
        state.tissues = model.load(state.tissues, stop_p, stop_time, back_gas, 0.0)
        state.cns_tracker.update(po2_stop, stop_time)
        state.otu_tracker.update(po2_stop, stop_time)
        if state.track_enabled:
            state.track_gas(back_gas, stop_time, stop_p, sac_bottom)
        state.runtime += stop_time
        descent_time += stop_time
        state.snapshot(model, stop_depth, model.gf_low)
        state.profile.append((round(state.runtime, 2), stop_depth))
        prev_depth = stop_depth

    # Final descent segment to target depth
    final_seg_time = (depth - prev_depth) / descent_rate
    seg_start_p = _depth_to_pressure(prev_depth, state.surface_pressure)
    state.tissues = model.load(
        state.tissues, seg_start_p, final_seg_time, back_gas, descent_rate_bar
    )
    avg_descent_pressure = (
        _depth_to_pressure(prev_depth, state.surface_pressure)
        + _depth_to_pressure(depth, state.surface_pressure)
    ) / 2.0
    po2_descent = (back_gas.o2 / 100.0) * avg_descent_pressure
    state.cns_tracker.update(po2_descent, final_seg_time)
    state.otu_tracker.update(po2_descent, final_seg_time)
    if state.track_enabled:
        state.track_gas(back_gas, final_seg_time, avg_descent_pressure, sac_bottom)
    state.runtime += final_seg_time
    descent_time += final_seg_time
    state.snapshot(model, depth, model.gf_low)
    state.profile.append((round(state.runtime, 2), depth))

    return descent_time


def _bottom(
    state: _DiveState,
    model: ZHL16GF,
    depth: float,
    bottom_duration: float,
    back_gas: Gas,
    sac_bottom: float,
) -> None:
    """Execute the bottom phase. Modifies state in place."""
    abs_p_bottom = _depth_to_pressure(depth, state.surface_pressure)
    po2_bottom = (back_gas.o2 / 100.0) * abs_p_bottom

    remaining = bottom_duration
    while remaining > 0:
        step = min(1.0, remaining)
        state.tissues = model.load(state.tissues, abs_p_bottom, step, back_gas, 0.0)
        state.cns_tracker.update(po2_bottom, step)
        state.otu_tracker.update(po2_bottom, step)
        if state.track_enabled:
            state.track_gas(back_gas, step, abs_p_bottom, sac_bottom)
        state.runtime += step
        remaining -= step
        state.snapshot(model, depth, model.gf_low)

    state.profile.append((round(state.runtime, 2), depth))
    state.max_gas_density = max(state.max_gas_density, _gas_density(back_gas, abs_p_bottom))


def _ascend_with_deco(
    state: _DiveState,
    model: ZHL16GF,
    depth: float,
    back_gas: Gas,
    deco_gases: list[Gas],
    ascent_rate: float,
    last_stop_depth: float,
    sac_bottom: float,
    sac_deco: float,
    gf_low: float,
    gf_high: float,
) -> tuple[list[DecoStop], float, float | None, dict[float, float], float]:
    """Execute ascent and deco phases.

    Returns (stops, total_deco_time, ndl, stop_runtimes, back_gas_ascent_litres).
    """
    sp = state.surface_pressure
    abs_p_bottom = _depth_to_pressure(depth, sp)
    ascent_rate_bar = ascent_rate * const.METER_TO_BAR
    all_gases = [back_gas] + sorted(deco_gases, key=lambda g: g.switch_depth, reverse=True)
    current_gas = back_gas

    # Determine ceiling
    ceiling_depth = _pressure_to_depth(model.ceiling(state.tissues, gf_low), sp)
    first_stop_depth = max(last_stop_depth, _ceil_to_3m(ceiling_depth))

    # Check if NDL dive
    test_ascent_time = depth / ascent_rate
    test_tissues = model.load(
        state.tissues, abs_p_bottom, test_ascent_time, current_gas, -ascent_rate_bar
    )
    surface_ceiling = model.ceiling(test_tissues, gf_high)

    if surface_ceiling <= sp:
        # NDL dive - compute remaining no-deco time via binary search
        ndl_lo, ndl_hi = 0.0, 600.0
        for _ in range(30):
            ndl_mid = (ndl_lo + ndl_hi) / 2.0
            t_tissues = model.load(state.tissues, abs_p_bottom, ndl_mid, current_gas, 0.0)
            t_ascent_time = depth / ascent_rate
            t_tissues_asc = model.load(
                t_tissues, abs_p_bottom, t_ascent_time, current_gas, -ascent_rate_bar
            )
            t_ceiling = model.ceiling(t_tissues_asc, gf_high)
            if t_ceiling <= sp:
                ndl_lo = ndl_mid
            else:
                ndl_hi = ndl_mid
        computed_ndl = round(ndl_lo, 0)

        # Ascend directly
        ascent_time = depth / ascent_rate
        avg_ascent_p = abs_p_bottom - (depth * const.METER_TO_BAR / 2.0)
        po2_ascent = (current_gas.o2 / 100.0) * avg_ascent_p
        state.cns_tracker.update(po2_ascent, ascent_time)
        state.otu_tracker.update(po2_ascent, ascent_time)
        if state.track_enabled:
            state.track_gas(current_gas, ascent_time, avg_ascent_p, sac_deco)
        state.tissues = test_tissues
        state.runtime += ascent_time
        state.snapshot(model, 0.0, gf_high)
        state.profile.append((round(state.runtime, 2), 0.0))

        return [], 0.0, computed_ndl, {}, 0.0

    # Deco dive - ascend to first stop
    total_deco_time = 0.0
    stops: list[DecoStop] = []
    stop_runtimes: dict[float, float] = {}
    back_gas_ascent_litres = 0.0
    on_back_gas = True

    # Free ascent to first stop
    ascent_to_first = depth - first_stop_depth
    if ascent_to_first > 0:
        free_ascent_time = ascent_to_first / ascent_rate
        state.tissues = model.load(
            state.tissues, abs_p_bottom, free_ascent_time, current_gas, -ascent_rate_bar
        )
        avg_p = abs_p_bottom - (ascent_to_first * const.METER_TO_BAR / 2.0)
        po2 = (current_gas.o2 / 100.0) * avg_p
        state.cns_tracker.update(po2, free_ascent_time)
        state.otu_tracker.update(po2, free_ascent_time)
        if state.track_enabled:
            state.track_gas(current_gas, free_ascent_time, avg_p, sac_deco)
        back_gas_ascent_litres += sac_bottom * free_ascent_time * (avg_p / state.surface_pressure)
        state.runtime += free_ascent_time
    state.snapshot(model, first_stop_depth, gf_low)
    state.profile.append((round(state.runtime, 2), first_stop_depth))

    # Process each 3m stop
    stop_depth = first_stop_depth
    while stop_depth >= last_stop_depth:
        abs_p_stop = _depth_to_pressure(stop_depth, sp)
        if first_stop_depth > 0:
            current_gf = (
                gf_low + (gf_high - gf_low) * (first_stop_depth - stop_depth) / first_stop_depth
            )
        else:
            current_gf = gf_high
        current_gf = min(current_gf, gf_high)

        next_stop_depth = stop_depth - 3.0
        if first_stop_depth > 0 and next_stop_depth > 0:
            next_gf = (
                gf_low
                + (gf_high - gf_low) * (first_stop_depth - next_stop_depth) / first_stop_depth
            )
        else:
            next_gf = gf_high
        next_gf = min(next_gf, gf_high)

        # Gas switch — pick richest O2 eligible gas
        best_gas = current_gas
        for g in all_gases[1:]:
            if g.switch_depth >= stop_depth and g.o2 > best_gas.o2:
                best_gas = g
        if best_gas != current_gas:
            current_gas = best_gas

        if current_gas != back_gas and on_back_gas:
            on_back_gas = False

        state.max_gas_density = max(state.max_gas_density, _gas_density(current_gas, abs_p_stop))

        # Wait at stop until we can ascend
        stop_time = 0.0
        while True:
            if stop_depth <= last_stop_depth:
                ascent_seg_time = stop_depth / ascent_rate
                test_tissues_stop = model.load(
                    state.tissues, abs_p_stop, ascent_seg_time, current_gas, -ascent_rate_bar
                )
                test_ceiling = model.ceiling(test_tissues_stop, gf_high)
                if test_ceiling <= sp:
                    break
            else:
                ascent_seg_time = 3.0 / ascent_rate
                test_tissues_stop = model.load(
                    state.tissues, abs_p_stop, ascent_seg_time, current_gas, -ascent_rate_bar
                )
                next_stop_p = _depth_to_pressure(stop_depth - 3.0, sp)
                test_ceiling = model.ceiling(test_tissues_stop, next_gf)
                if test_ceiling <= next_stop_p:
                    break

            # Stay 1 more minute
            state.tissues = model.load(state.tissues, abs_p_stop, 1.0, current_gas, 0.0)
            po2 = (current_gas.o2 / 100.0) * abs_p_stop
            state.cns_tracker.update(po2, 1.0)
            state.otu_tracker.update(po2, 1.0)
            if state.track_enabled:
                state.track_gas(current_gas, 1.0, abs_p_stop, sac_deco)
            if on_back_gas:
                back_gas_ascent_litres += sac_bottom * 1.0 * (abs_p_stop / state.surface_pressure)
            stop_time += 1.0
            state.runtime += 1.0

        if stop_time > 0:
            stops.append(DecoStop(depth=stop_depth, time=stop_time))
            total_deco_time += stop_time
            stop_runtimes[stop_depth] = round(state.runtime, 2)
        state.snapshot(model, stop_depth, current_gf)
        state.profile.append((round(state.runtime, 2), stop_depth))

        # Ascend 3m
        if stop_depth <= last_stop_depth:
            ascent_time = stop_depth / ascent_rate
            state.tissues = model.load(
                state.tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (stop_depth * const.METER_TO_BAR / 2.0)
            next_profile_depth = 0.0
        else:
            ascent_time = 3.0 / ascent_rate
            state.tissues = model.load(
                state.tissues, abs_p_stop, ascent_time, current_gas, -ascent_rate_bar
            )
            avg_p = abs_p_stop - (3.0 * const.METER_TO_BAR / 2.0)
            next_profile_depth = stop_depth - 3.0

        po2 = (current_gas.o2 / 100.0) * avg_p
        state.cns_tracker.update(po2, ascent_time)
        state.otu_tracker.update(po2, ascent_time)
        if state.track_enabled:
            state.track_gas(current_gas, ascent_time, avg_p, sac_deco)
        if on_back_gas:
            back_gas_ascent_litres += sac_bottom * ascent_time * (avg_p / state.surface_pressure)
        state.runtime += ascent_time
        state.snapshot(model, next_profile_depth, next_gf)
        state.profile.append((round(state.runtime, 2), next_profile_depth))

        if stop_depth <= last_stop_depth:
            break
        stop_depth -= 3.0

    return stops, total_deco_time, None, stop_runtimes, back_gas_ascent_litres


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
    max_po2: float = 1.61,
    max_deco_time: float = 1440.0,
) -> DiveSummary:
    """Plan a dive and return a complete summary.

    This is the primary high-level API for DecoTengu. It configures the
    decompression model, runs the calculation, and returns all commonly
    needed results in a single call.

    :param depth: Maximum dive depth [m].
    :param bottom_time: Bottom time [min] (from surface to leaving bottom).
    :param back_gas: Back gas mix. Default is Air (21/0).
    :param deco_gases: List of decompression gas mixes with switch depths set.
    :param gf: Gradient factors as (low, high) percentages in range (0, 100].
        Example: (30, 85). GF low must be <= GF high.
    :param descent_rate: Descent rate [m/min]. Default 20.
    :param ascent_rate: Ascent rate [m/min]. Default 10.
    :param last_stop_depth: Depth of last deco stop [m]. Default 3.
    :param model: Decompression model class or instance. Default ZHL16C.
    :param surface_pressure: Surface pressure [bar]. Default 1.01325 (sea level).
        For altitude diving, use a lower value (e.g. 0.825 bar ≈ 1800m altitude).
        Valid range: 0.5–1.1 bar.
    :param cns_method: CNS calculation method. Default EXPONENTIAL.
    :param sac_bottom: Surface-equivalent SAC [L/min] for descent and bottom. Default 20.
    :param sac_deco: Surface-equivalent SAC [L/min] for deco stops and ascent. Default 17.
    :param back_cylinder: Back gas cylinder. If provided, gas_usage is populated.
    :param deco_cylinders: Deco gas cylinders, parallel to deco_gases list.
    :param descent_stops: Optional list of (depth_m, time_min) stops to make during
        descent (e.g. S-drill at 5m). Stops are sorted by depth and must be shallower
        than the target depth. Tissue loading is computed correctly for each segment.
    :param max_po2: Maximum allowed PO2 for deco gas switches [bar]. Default 1.61
        (accommodates standard O2 at 6m in seawater). Set lower for more
        conservative limits or higher for advanced configurations.
    :param max_deco_time: Maximum total decompression time [min] before raising an error.
        Default 1440 (24 hours). Acts as a safety limit against runaway calculations.
    :returns: DiveSummary with all dive information.
    """
    if back_gas is None:
        back_gas = Gas(o2=21, he=0)
    if deco_gases is None:
        deco_gases = []

    # --- Validate and resolve ---
    gf_low, gf_high = _validate_inputs(
        depth,
        bottom_time,
        descent_rate,
        ascent_rate,
        last_stop_depth,
        sac_bottom,
        sac_deco,
        gf,
        deco_gases,
        surface_pressure,
        max_po2,
    )
    deco_model = _resolve_model(model, gf_low, gf_high)

    # --- Build state ---
    state = _DiveState(
        tissues=deco_model.init(surface_pressure),
        cns_tracker=CNSTracker(method=cns_method),
        otu_tracker=OTUTracker(),
        surface_pressure=surface_pressure,
        track_enabled=back_cylinder is not None or deco_cylinders is not None,
    )

    # Cylinder setup
    if state.track_enabled:
        all_divegases_list = [back_gas] + (deco_gases or [])
        all_cyls_list = ([back_cylinder] if back_cylinder else []) + (
            deco_cylinders if deco_cylinders else []
        )
        if len(all_divegases_list) != len(all_cyls_list):
            raise ValueError(
                f"Number of gases ({len(all_divegases_list)}) does not match "
                f"number of cylinders ({len(all_cyls_list)}). "
                f"Provide one cylinder per gas (1 back + {len(deco_gases)} deco), "
                f"or omit cylinders entirely."
            )
        for dg, dc in zip(all_divegases_list, all_cyls_list, strict=True):
            state.cylinders_by_label[_gas_label(dg)] = dc
        for lbl, cyl in state.cylinders_by_label.items():
            state.gas_pressure_profile[lbl] = [(0.0, round(cyl.fill_bar, 1))]

    # --- Descent ---
    descent_time = _descend(
        state,
        deco_model,
        depth,
        descent_rate,
        back_gas,
        sac_bottom,
        descent_stops,
    )

    # --- Bottom ---
    bottom_duration = bottom_time - descent_time
    if bottom_duration <= 0:
        raise ValueError("Bottom time must be greater than descent time")
    _bottom(state, deco_model, depth, bottom_duration, back_gas, sac_bottom)

    # --- Ascent ---
    stops, total_deco_time, ndl, stop_runtimes, back_gas_ascent_litres = _ascend_with_deco(
        state,
        deco_model,
        depth,
        back_gas,
        deco_gases,
        ascent_rate,
        last_stop_depth,
        sac_bottom,
        sac_deco,
        gf_low,
        gf_high,
    )

    if total_deco_time > max_deco_time:
        raise ValueError(
            f"Total deco time ({total_deco_time:.0f} min) exceeds "
            f"max_deco_time ({max_deco_time:.0f} min). "
            f"Check dive parameters or increase max_deco_time."
        )

    # --- Build gas_usage ---
    gas_usage: dict[str, GasUsage] = {}
    if state.track_enabled:
        all_divegases = [back_gas] + (deco_gases or [])
        _cyl_list: list[Cylinder | None] = []
        if back_cylinder:
            _cyl_list.append(back_cylinder)
        if deco_cylinders:
            _cyl_list.extend(deco_cylinders)
        for i, g in enumerate(all_divegases):
            lbl = _gas_label(g)
            cyl_i: Cylinder | None = _cyl_list[i] if i < len(_cyl_list) else None
            consumed = state.gas_consumed.get(lbl, 0.0)
            if cyl_i is not None:
                gas_usage[lbl] = GasUsage(gas=g, cylinder=cyl_i, consumed_litres=consumed)

    return DiveSummary(
        runtime=round(state.runtime, 1),
        total_deco_time=round(total_deco_time, 1),
        stops=stops,
        max_depth=depth,
        tissues_final=state.tissues,
        cns_percent=round(state.cns_tracker.cns_percent, 1),
        otu=round(state.otu_tracker.otu, 1),
        ndl=ndl,
        gas_usage=gas_usage,
        max_gas_density=round(state.max_gas_density, 3),
        stop_runtimes=stop_runtimes,
        profile=state.profile,
        back_gas_ascent_litres=round(back_gas_ascent_litres, 2),
        ceiling_profile=state.ceiling_profile,
        gas_pressure_profile=state.gas_pressure_profile,
    )
