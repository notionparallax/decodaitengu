"""
Dive planner using decotengu for Bühlmann ZH-L16B-GF decompression calculations.
"""
from decodaitengu.planning import plan_dive as _plan_dive
from decodaitengu.types import Gas as _Gas, Cylinder as _Cylinder
import matplotlib.pyplot as plt
from dataclasses import dataclass


# === Dataclasses ===

@dataclass
class GasConfig:
    o2: int
    he: int


@dataclass
class CylinderConfig:
    gas: GasConfig
    volume_l: float
    fill_pressure_bar: int
    name: str


@dataclass
class DiveConfig:
    depth: float
    bottom_time: float
    gf_low: float = 0.50
    gf_high: float = 0.70
    descent_rate: float = 20
    ascent_rate: float = 10


# === Configuration ===
GF_LOW = 0.50
GF_HIGH = 0.70  # changed from 0.80
DESCENT_RATE = 20  # m/min
ASCENT_RATE = 10   # m/min
SAC_BOTTOM = 20    # L/min at surface
SAC_DECO = 17      # L/min at surface
SURFACE_PRESSURE = 1.01325  # bar
WATER_TEMP_C = 18  # degrees C (working temperature)
FILL_TEMP_C = 40   # degrees C (tank temperature after filling)

# Cylinders (legacy constants)
BACK_GAS_VOL = 24.4   # litres
BACK_GAS_PRESSURE = 210  # bar
BACK_GAS_AVAILABLE = BACK_GAS_VOL * BACK_GAS_PRESSURE

DECO_O2_VOL = 11.1    # litres
DECO_O2_PRESSURE = 200  # bar
DECO_O2_AVAILABLE = DECO_O2_VOL * DECO_O2_PRESSURE

DECO_50_VOL = 11.1    # litres
DECO_50_PRESSURE = 200  # bar
DECO_50_AVAILABLE = DECO_50_VOL * DECO_50_PRESSURE

# Gas mixes (legacy tuples)
BACK_GAS = (22, 27)   # O2%, He% - Trimix 22/27
DECO_50 = (50, 0)     # EAN50
DECO_O2 = (100, 0)    # Pure O2

# Default switch depths
_DECO_50_SWITCH_DEPTH = 21
_DECO_O2_SWITCH_DEPTH = 6

# Cylinder dataclass instances
BACK_GAS_CYLINDER = CylinderConfig(GasConfig(23, 25), 24.4, 210, "Back Gas")
DECO_50_CYLINDER = CylinderConfig(GasConfig(50, 0), 11.1, 150, "EAN50")
DECO_O2_CYLINDER = CylinderConfig(GasConfig(100, 0), 11.1, 150, "O2")


def run_profile(depth, bottom_time, deco_gases_lost=False,
               back_gas=None, deco_cylinders_config=None,
               gf_low=None, gf_high=None,
               descent_rate=None, ascent_rate=None,
               sac_bottom=None, sac_deco=None,
               back_gas_pressure=None, deco_50_pressure=None, deco_o2_pressure=None,
               descent_stops=None):
    """Run a decompression calculation and return a DiveSummary.

    Args:
        deco_cylinders_config: list of (o2, he, switch_depth_m) tuples.
                               When provided, deco_gases_lost is ignored.
        back_gas: (o2, he) tuple; defaults to BACK_GAS_CYLINDER gas.
        descent_stops: list of (depth_m, time_min) stops during descent (e.g. S-drills).
    """
    _gf_low = gf_low if gf_low is not None else GF_LOW
    _gf_high = gf_high if gf_high is not None else GF_HIGH
    _descent_rate = descent_rate if descent_rate is not None else DESCENT_RATE
    _ascent_rate = ascent_rate if ascent_rate is not None else ASCENT_RATE
    _back_gas = back_gas if back_gas is not None else (BACK_GAS_CYLINDER.gas.o2, BACK_GAS_CYLINDER.gas.he)
    _sac_bottom = sac_bottom if sac_bottom is not None else SAC_BOTTOM
    _sac_deco = sac_deco if sac_deco is not None else SAC_DECO
    _back_gas_pressure = back_gas_pressure if back_gas_pressure is not None else BACK_GAS_PRESSURE
    _deco_50_pressure = deco_50_pressure if deco_50_pressure is not None else DECO_50_PRESSURE
    _deco_o2_pressure = deco_o2_pressure if deco_o2_pressure is not None else DECO_O2_PRESSURE

    back_gas_obj = _Gas(o2=_back_gas[0], he=_back_gas[1], label='back')
    back_cyl_obj = _Cylinder(volume_litres=BACK_GAS_VOL, fill_bar=_back_gas_pressure)

    if deco_cylinders_config is not None:
        _deco_gases_raw = deco_cylinders_config
    else:
        _deco_gases_raw = []
        if deco_gases_lost not in (True, 'ean50'):
            _deco_gases_raw.append((50, 0, _DECO_50_SWITCH_DEPTH))
        if deco_gases_lost not in (True, 'o2'):
            _deco_gases_raw.append((100, 0, _DECO_O2_SWITCH_DEPTH))

    deco_gas_objs = []
    deco_cyl_objs = []
    for o2, he, sd in _deco_gases_raw:
        if o2 == 50 and he == 0:
            label, vol, pressure = 'ean50', DECO_50_VOL, _deco_50_pressure
        elif o2 == 100 and he == 0:
            label, vol, pressure = 'o2', DECO_O2_VOL, _deco_o2_pressure
        else:
            label, vol, pressure = f'tx{o2}/{he}', DECO_50_VOL, _deco_50_pressure
        deco_gas_objs.append(_Gas(o2=o2, he=he, switch_depth=float(sd), label=label))
        deco_cyl_objs.append(_Cylinder(volume_litres=vol, fill_bar=pressure))

    return _plan_dive(
        depth=depth,
        bottom_time=bottom_time,
        back_gas=back_gas_obj,
        deco_gases=deco_gas_objs,
        gf=(_gf_low * 100, _gf_high * 100),
        descent_rate=_descent_rate,
        ascent_rate=_ascent_rate,
        sac_bottom=_sac_bottom,
        sac_deco=_sac_deco,
        back_cylinder=back_cyl_obj,
        deco_cylinders=deco_cyl_objs,
        descent_stops=descent_stops,
    )


def format_gas_bar(used_litres, cylinder_vol, cylinder_pressure):
    """Convert litres used to bar remaining."""
    bar_used = used_litres / cylinder_vol
    remaining = cylinder_pressure - bar_used
    return remaining


def calculate_min_gas_and_turn_from_summary(summary, back_gas_pressure, back_gas_vol=None,
                                             sac_bottom=None):
    """Calculate minimum gas (2 divers ascending on back gas) and turn pressure from DiveSummary.

    Args:
        summary: DiveSummary from run_profile().
        back_gas_pressure: Fill pressure of back gas cylinder [bar].
        back_gas_vol: Volume of back gas cylinder [L]. Defaults to BACK_GAS_VOL.
        sac_bottom: SAC for stressed breathing [L/min]. Defaults to SAC_BOTTOM.
    """
    _back_gas_vol = back_gas_vol if back_gas_vol is not None else BACK_GAS_VOL
    _sac_bottom = sac_bottom if sac_bottom is not None else SAC_BOTTOM

    depth = summary.max_depth
    abs_p_bottom = SURFACE_PRESSURE + depth / 10.0

    # Gas used during descent + bottom (before ascent starts)
    if len(summary.profile) >= 3:
        descent_time = summary.profile[1][0]
        bottom_leave_time = summary.profile[2][0]
        bottom_duration = bottom_leave_time - descent_time
    else:
        descent_time = depth / DESCENT_RATE
        bottom_duration = 0.0

    avg_descent_p = (SURFACE_PRESSURE + abs_p_bottom) / 2.0
    gas_descent = _sac_bottom * descent_time * avg_descent_p / SURFACE_PRESSURE
    gas_bottom = _sac_bottom * bottom_duration * abs_p_bottom / SURFACE_PRESSURE
    gas_used_before_ascent = gas_descent + gas_bottom
    bar_used_before_ascent = gas_used_before_ascent / _back_gas_vol
    bar_at_turn = back_gas_pressure - bar_used_before_ascent

    # Min gas = (1 min problem-solving at depth + ascent back gas) x 2 divers
    ascent_back_gas_one = summary.back_gas_ascent_litres
    problem_solve_one = _sac_bottom * 1.0 * abs_p_bottom / SURFACE_PRESSURE
    min_gas_litres = (ascent_back_gas_one + problem_solve_one) * 2
    turn_pressure_bar = min_gas_litres / _back_gas_vol

    return {
        'min_gas_litres': min_gas_litres,
        'turn_pressure_bar': turn_pressure_bar,
        'bar_at_turn': bar_at_turn,
        'bar_used_bottom': bar_used_before_ascent,
        'can_start_before_140': bar_at_turn >= 140,
        'has_enough_gas': bar_at_turn >= turn_pressure_bar,
    }


def run_scenario(name, depth, bottom_time, deco_gases_lost=False, cfg=None,
                 back_gas=None,
                 back_gas_pressure=None, deco_50_pressure=None, deco_o2_pressure=None,
                 gf_low=None, gf_high=None, descent_rate=None, ascent_rate=None,
                 sac_bottom=None, sac_deco=None,
                 descent_stops=None):
    """Run a complete scenario and return results dict.

    cfg: optional dict with keys:
        back_cylinder: CylinderConfig
        deco_cylinders: list of (CylinderConfig, switch_depth_m)
        gf_low, gf_high: float
        descent_rate, ascent_rate: float
        sac_bottom, sac_deco: float
    back_gas_pressure: override fill pressure for back gas (default: BACK_GAS_PRESSURE)
    deco_50_pressure: override fill pressure for EAN50 (default: DECO_50_PRESSURE)
    deco_o2_pressure: override fill pressure for O2 (default: DECO_O2_PRESSURE)
    descent_stops: list of (depth_m, time_min) stops during descent (e.g. S-drills).
    When cfg is provided, also returns 'cylinders' and 'steps' (None) in the result.
    """
    _back_gas_pressure = back_gas_pressure if back_gas_pressure is not None else BACK_GAS_PRESSURE
    _deco_50_pressure = deco_50_pressure if deco_50_pressure is not None else DECO_50_PRESSURE
    _deco_o2_pressure = deco_o2_pressure if deco_o2_pressure is not None else DECO_O2_PRESSURE
    _cfg = cfg or {}
    _sac_bottom = sac_bottom if sac_bottom is not None else (_cfg.get('sac_bottom') if _cfg.get('sac_bottom') is not None else SAC_BOTTOM)
    _sac_deco = sac_deco if sac_deco is not None else (_cfg.get('sac_deco') if _cfg.get('sac_deco') is not None else SAC_DECO)
    _gf_low = gf_low if gf_low is not None else _cfg.get('gf_low', GF_LOW)
    _gf_high = gf_high if gf_high is not None else _cfg.get('gf_high', GF_HIGH)
    _descent_rate = descent_rate if descent_rate is not None else _cfg.get('descent_rate', DESCENT_RATE)
    _ascent_rate = ascent_rate if ascent_rate is not None else _cfg.get('ascent_rate', ASCENT_RATE)

    back_cyl = _cfg.get('back_cylinder') or BACK_GAS_CYLINDER
    deco_cyls_with_depths = _cfg.get('deco_cylinders')
    # Use explicitly passed back_gas if provided, otherwise fall back to BACK_GAS_CYLINDER
    if back_gas is not None:
        back_gas_tuple = back_gas
    else:
        back_gas_tuple = (back_cyl.gas.o2, back_cyl.gas.he)

    if cfg is not None:
        # cfg path: build Gas/Cylinder objects from CylinderConfig objects
        _back_gas_pressure = back_cyl.fill_pressure_bar
        back_gas_obj = _Gas(o2=back_cyl.gas.o2, he=back_cyl.gas.he, label=back_cyl.name)
        back_cyl_obj = _Cylinder(volume_litres=back_cyl.volume_l, fill_bar=back_cyl.fill_pressure_bar)

        deco_gas_objs = []
        deco_cyl_objs = []
        has_switch_stop = False
        switch_depth = _DECO_50_SWITCH_DEPTH
        if deco_cyls_with_depths is not None:
            first_non_o2 = next(((c, sd) for c, sd in deco_cyls_with_depths if c.gas.o2 < 100), None)
            has_switch_stop = first_non_o2 is not None
            if has_switch_stop:
                switch_depth = float(first_non_o2[1])
            for cyl, sd in deco_cyls_with_depths:
                deco_gas_objs.append(_Gas(o2=cyl.gas.o2, he=cyl.gas.he, switch_depth=float(sd), label=cyl.name))
                deco_cyl_objs.append(_Cylinder(volume_litres=cyl.volume_l, fill_bar=cyl.fill_pressure_bar))

        summary = _plan_dive(
            depth=depth,
            bottom_time=bottom_time,
            back_gas=back_gas_obj,
            deco_gases=deco_gas_objs,
            gf=(_gf_low * 100, _gf_high * 100),
            descent_rate=_descent_rate,
            ascent_rate=_ascent_rate,
            sac_bottom=_sac_bottom,
            sac_deco=_sac_deco,
            back_cylinder=back_cyl_obj,
            deco_cylinders=deco_cyl_objs,
            descent_stops=descent_stops,
        )

        all_cylinders_list = [back_cyl] + ([c for c, _ in deco_cyls_with_depths] if deco_cyls_with_depths else [])
        cylinders_result = []
        for cyl in all_cylinders_list:
            usage = summary.gas_usage.get(cyl.name)
            used_litres = usage.consumed_litres if usage else 0.0
            bar_used = used_litres / cyl.volume_l
            remaining_bar = cyl.fill_pressure_bar - bar_used
            cylinders_result.append({
                'name': cyl.name,
                'gas': {'o2': cyl.gas.o2, 'he': cyl.gas.he},
                'volume_l': cyl.volume_l,
                'fill_bar': cyl.fill_pressure_bar,
                'used_litres': used_litres,
                'used_bar': bar_used,
                'remaining_bar': remaining_bar,
            })

        min_gas = calculate_min_gas_and_turn_from_summary(
            summary,
            back_gas_pressure=_back_gas_pressure,
            back_gas_vol=back_cyl.volume_l,
            sac_bottom=_sac_bottom,
        )

        back_remaining = cylinders_result[0]['remaining_bar'] if cylinders_result else None
        ean50_remaining = next(
            (c['remaining_bar'] for c in cylinders_result if c['gas']['o2'] == 50 and c['gas']['he'] == 0), None)
        o2_remaining = next(
            (c['remaining_bar'] for c in cylinders_result if c['gas']['o2'] == 100), None)
        gas_used = {c['name']: {'litres': c['used_litres'], 'bar': c['used_bar']}
                    for c in cylinders_result}
    else:
        # Non-cfg path: use run_profile with default gas labels
        summary = run_profile(
            depth, bottom_time, deco_gases_lost,
            back_gas=back_gas_tuple,
            gf_low=_gf_low, gf_high=_gf_high,
            descent_rate=_descent_rate, ascent_rate=_ascent_rate,
            sac_bottom=_sac_bottom, sac_deco=_sac_deco,
            back_gas_pressure=_back_gas_pressure,
            deco_50_pressure=_deco_50_pressure,
            deco_o2_pressure=_deco_o2_pressure,
            descent_stops=descent_stops,
        )

        back_usage = summary.gas_usage.get('back')
        ean50_usage = summary.gas_usage.get('ean50')
        o2_usage = summary.gas_usage.get('o2')

        back_remaining = back_usage.remaining_bar if back_usage else _back_gas_pressure
        ean50_remaining = ean50_usage.remaining_bar if ean50_usage else _deco_50_pressure
        o2_remaining = o2_usage.remaining_bar if o2_usage else _deco_o2_pressure

        gas_used = {
            'back_gas': back_usage.consumed_litres if back_usage else 0.0,
            'ean50': ean50_usage.consumed_litres if ean50_usage else 0.0,
            'o2': o2_usage.consumed_litres if o2_usage else 0.0,
        }

        min_gas = calculate_min_gas_and_turn_from_summary(
            summary,
            back_gas_pressure=_back_gas_pressure,
            back_gas_vol=BACK_GAS_VOL,
            sac_bottom=_sac_bottom,
        )

        has_switch_stop = deco_gases_lost not in (True, 'ean50')
        switch_depth = _DECO_50_SWITCH_DEPTH
        cylinders_result = None

    # Build deco_stops and apply switch stop
    deco_stops = [(s.depth, s.time) for s in summary.stops]
    total_time = summary.runtime
    total_deco = summary.total_deco_time
    stop_runtimes = dict(summary.stop_runtimes)

    if has_switch_stop and summary.stops:
        deco_stops.insert(0, (float(switch_depth), 1.0))
        total_deco += 1.0
        total_time += 1.0
        stop_runtimes = {d: rt + 1.0 for d, rt in stop_runtimes.items()}
        # Add runtime for the EAN50 gas-switch stop: first profile point at/shallower
        # than the switch depth, plus 1 min for the switch stop itself
        _sw = float(switch_depth)
        switch_pts = [(t, d) for t, d in summary.profile if 0 < d <= _sw + 0.5]
        if switch_pts:
            stop_runtimes[_sw] = round(switch_pts[0][0] + 1.0, 1)

    profile_times = [t for t, d in summary.profile]
    profile_depths = [d for t, d in summary.profile]

    result = {
        'name': name,
        'depth': depth,
        'bottom_time': bottom_time,
        'total_time': total_time,
        'total_deco': total_deco,
        'deco_stops': deco_stops,
        'times': profile_times,
        'depths': profile_depths,
        'deco_gases_lost': deco_gases_lost,
        'stop_runtimes': stop_runtimes,
        'otu': summary.otu,
        'cns': summary.cns_percent,
        'gas_used': gas_used,
        'back_remaining_bar': back_remaining,
        'ean50_remaining_bar': ean50_remaining,
        'o2_remaining_bar': o2_remaining,
        'min_gas': min_gas,
        'max_gas_density': summary.max_gas_density,
    }
    result['ceiling_profile'] = summary.ceiling_profile
    result['gas_pressure_profile'] = summary.gas_pressure_profile

    if cfg is not None:
        result['cylinders'] = cylinders_result
        result['steps'] = None

    return result


def print_table(results):
    """Print a comparison table of all scenarios."""
    # Header
    col_width = 18
    header = f"{'Parameter':<25}"
    for r in results:
        header += f"{r['name']:>{col_width}}"
    print(header)
    print("=" * len(header))

    # Rows
    rows = [
        ("Depth (m)", lambda r: f"{r['depth']}"),
        ("Bottom time (min)", lambda r: f"{r['bottom_time']}"),
        ("Total deco (min)", lambda r: f"{r['total_deco']:.0f}"),
        ("Total runtime (min)", lambda r: f"{r['total_time']:.1f}"),
        ("", lambda r: ""),
    ]

    # Add deco stop rows - gather all unique depths
    all_stop_depths = set()
    for r in results:
        for depth, time in r['deco_stops']:
            all_stop_depths.add(depth)
    for d in sorted(all_stop_depths, reverse=True):
        rows.append((
            f"  Stop {d:.0f}m (min)",
            lambda r, d=d: next((f"{t:.0f}" for dp, t in r['deco_stops'] if dp == d), "-")
        ))

    rows.extend([
        ("", lambda r: ""),
        ("Back gas used (bar)", lambda r: f"{(BACK_GAS_PRESSURE - r['back_remaining_bar']):.0f}"),
        ("Back gas remaining (bar)", lambda r: f"{r['back_remaining_bar']:.0f}"),
        ("EAN50 used (bar)", lambda r: f"{(DECO_50_PRESSURE - r['ean50_remaining_bar']):.0f}" if r['deco_gases_lost'] not in (True, 'ean50') else "N/A"),
        ("EAN50 remaining (bar)", lambda r: f"{r['ean50_remaining_bar']:.0f}" if r['deco_gases_lost'] not in (True, 'ean50') else "N/A"),
        ("O2 used (bar)", lambda r: f"{(DECO_O2_PRESSURE - r['o2_remaining_bar']):.0f}" if r['deco_gases_lost'] not in (True, 'o2') else "N/A"),
        ("O2 remaining (bar)", lambda r: f"{r['o2_remaining_bar']:.0f}" if r['deco_gases_lost'] not in (True, 'o2') else "N/A"),
        ("", lambda r: ""),
        ("--- O2 TOXICITY ---", lambda r: ""),
        ("OTU", lambda r: f"{r['otu']:.0f}"),
        ("CNS %", lambda r: f"{r['cns']:.0f}%"),
        ("", lambda r: ""),
        ("--- RULE OF THIRDS ---", lambda r: ""),
        ("Thirds turn (bar)", lambda r: f"{BACK_GAS_PRESSURE * 2 // 3:.0f}"),
        ("Bar at turn (actual)", lambda r: f"{r['min_gas']['bar_at_turn']:.0f}"),
        ("Turns within thirds?", lambda r: "YES" if r['min_gas']['bar_at_turn'] >= (BACK_GAS_PRESSURE * 2 / 3) else "NO"),
        ("", lambda r: ""),
        ("--- END GAS ---", lambda r: ""),
        ("End: Back/50/O2 (bar)", lambda r:
            f"{r['back_remaining_bar']:.0f}/{r['ean50_remaining_bar']:.0f}/{r['o2_remaining_bar']:.0f}"
            if r['deco_gases_lost'] is False else
            f"{r['back_remaining_bar']:.0f}/--/{r['o2_remaining_bar']:.0f}"
            if r['deco_gases_lost'] == 'ean50' else
            f"{r['back_remaining_bar']:.0f}/{r['ean50_remaining_bar']:.0f}/--"
            if r['deco_gases_lost'] == 'o2' else
            f"{r['back_remaining_bar']:.0f}/--/--"),
    ])

    for label, fn in rows:
        line = f"{label:<25}"
        for r in results:
            line += f"{fn(r):>{col_width}}"
        print(line)


def plot_profiles(results):
    """Create a line graph with a table below it showing deco stop runtimes."""
    from matplotlib.ticker import FuncFormatter

    # Build table data first to determine row count for sizing
    bottom_depths = sorted(set(r['depth'] for r in results), reverse=True)
    all_stop_depths = sorted(
        set(d for r in results for d, t in r['deco_stops']), reverse=True
    )
    num_table_rows = len(bottom_depths) + len(all_stop_depths) + 1  # +1 for header

    # Size figure: plot on top, table below
    fig, (ax_plot, ax_table) = plt.subplots(
        2, 1, figsize=(24, 14),
        gridspec_kw={'height_ratios': [2, 1]},
    )

    # --- Plot ---
    for r in results:
        ax_plot.plot(r['times'], [-d for d in r['depths']], label=r['name'], linewidth=1.5)

    ax_plot.set_xlabel('Time (minutes)', fontsize=18)
    ax_plot.set_ylabel('Depth (metres)', fontsize=18)
    ax_plot.set_title('Dive Profile Comparison - Trimix 23/25, GF 50/70', fontsize=18)
    ax_plot.legend(loc='lower right', fontsize=18, ncol=6)
    ax_plot.grid(True, alpha=0.3)
    ax_plot.axhline(y=0, color='lightblue', linewidth=2, alpha=0.5)
    ax_plot.tick_params(axis='both', labelsize=18)
    ax_plot.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{abs(y):.0f}"))

    # --- Table ---
    ax_table.axis('off')

    col_labels = [r['name'] for r in results]
    row_labels = ([f"{d:.0f}m" for d in bottom_depths]
                  + [f"{d:.0f}m" for d in all_stop_depths]
                  + ['OTU', 'CNS%'])

    cell_text = []

    # Bottom depth rows
    for bd in bottom_depths:
        row = []
        for r in results:
            if r['depth'] == bd:
                row.append(f"{r['bottom_time']}")
            else:
                row.append("-")
        cell_text.append(row)

    # Deco stop rows
    for d in all_stop_depths:
        row = []
        for r in results:
            stop_time = next((t for dp, t in r['deco_stops'] if dp == d), None)
            if stop_time is None:
                row.append("-")
            else:
                rt_info = r['stop_runtimes'].get(d)
                if rt_info is not None:
                    row.append(f"{rt_info:.0f} ({stop_time:.0f})")
                else:
                    row.append(f"({stop_time:.0f})")
        cell_text.append(row)

    # OTU and CNS rows
    cell_text.append([f"{r['otu']:.0f}" for r in results])
    cell_text.append([f"{r['cns']:.0f}%" for r in results])

    table = ax_table.table(
        cellText=cell_text,
        rowLabels=row_labels,
        colLabels=col_labels,
        cellLoc='center',
        loc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(16)
    table.scale(1, 1.4)

    # Style the table
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#cccccc')
        cell.set_linewidth(0.5)
        if row == 0:
            cell.set_facecolor('#e6e6e6')
            cell.set_text_props(weight='bold', fontsize=14)
        elif col == -1:
            cell.set_facecolor('#f0f0f0')
            cell.set_text_props(weight='bold')
        else:
            cell.set_facecolor('#ffffff')
        cell.set_alpha(0.9)
        cell.PAD = 0.02

    plt.tight_layout()
    plt.savefig('dive_profiles.png', dpi=150, bbox_inches='tight')
    print("\nProfile chart saved to: dive_profiles.png")
    plt.close()


def calculate_best_mix(depth, target_end=30, max_po2_bottom=1.4):
    """
    Calculate the optimal trimix for a given depth.

    Uses the narcotic-O2 model: END = (depth + 10) × (1 - He_frac) - 10
    O2 is set to maximum allowable at depth (capped by max_po2_bottom).

    Returns:
        dict with o2%, he%, n2%, actual END, actual PO2 at depth
    """
    ambient_bar = SURFACE_PRESSURE + depth / 10.0
    ambient_ata = ambient_bar / SURFACE_PRESSURE

    # O2%: max allowed by PO2 limit
    o2_frac = max_po2_bottom / ambient_bar
    o2_pct = int(o2_frac * 100)  # round down for safety
    o2_frac = o2_pct / 100.0

    # He% from END formula: END = (depth + 10) × (1 - He_frac) - 10
    # Solve for He_frac: He_frac = 1 - (END + 10) / (depth + 10)
    he_frac = 1.0 - (target_end + 10.0) / (depth + 10.0)
    he_frac = max(0.0, he_frac)
    he_pct = round(he_frac * 100)
    he_frac = he_pct / 100.0

    # Verify N2 is non-negative
    n2_frac = 1.0 - o2_frac - he_frac
    if n2_frac < 0:
        # Too much He + O2; reduce He to fit
        he_frac = 1.0 - o2_frac
        he_pct = int(he_frac * 100)
        he_frac = he_pct / 100.0
        n2_frac = 1.0 - o2_frac - he_frac

    n2_pct = 100 - o2_pct - he_pct

    # Actual values
    actual_po2 = ambient_bar * o2_frac
    actual_end = (depth + 10) * (1 - he_frac) - 10

    return {
        'o2': o2_pct,
        'he': he_pct,
        'n2': n2_pct,
        'po2_at_depth': actual_po2,
        'end': actual_end,
        'depth': depth,
        'target_end': target_end,
        'max_po2': max_po2_bottom,
    }


def _gas_density_gl(o2_pct, he_pct, depth_m):
    """Gas density [g/L] at depth using ideal gas law at 37°C body temperature."""
    MW_O2, MW_N2, MW_HE = 31.998, 28.014, 4.003
    R, T = 0.083145, 310.15
    f_o2, f_he = o2_pct / 100.0, he_pct / 100.0
    mw_mix = f_o2 * MW_O2 + (1.0 - f_o2 - f_he) * MW_N2 + f_he * MW_HE
    abs_p = SURFACE_PRESSURE + depth_m / 10.0
    return (mw_mix * abs_p) / (R * T)


def calculate_deco_switch_depth(o2_pct, max_po2_deco=1.6):
    """Calculate the maximum switch depth for a deco gas, rounded down to nearest 3m."""
    o2_frac = o2_pct / 100.0
    # MOD = (max_po2 / o2_frac) in bar absolute, converted to depth
    max_depth_bar = max_po2_deco / o2_frac
    max_depth = (max_depth_bar - SURFACE_PRESSURE) * 10
    # Round down to nearest 3m (standard stop depths)
    return int(max_depth / 3) * 3


def optimize_deco_gases(depth, bottom_time, back_gas=None, target_end=30,
                        max_po2_bottom=1.4, max_po2_deco=1.6,
                        gf_low=None, gf_high=None):
    """
    Find the optimal intermediate deco gas (with pure O2 as second gas) that
    minimizes total runtime for a given depth/bottom time.

    Tries intermediate gases from 35% to 80% O2, each at its MOD.
    Pure O2 is always the shallow deco gas at 6m.

    Returns:
        dict with best intermediate gas, switch depths, total runtime comparison
    """
    _gf_low = gf_low if gf_low is not None else GF_LOW
    _gf_high = gf_high if gf_high is not None else GF_HIGH

    # Calculate best back gas for this depth
    mix = calculate_best_mix(depth, target_end, max_po2_bottom)
    _back_gas = back_gas if back_gas is not None else (mix['o2'], mix['he'])

    # O2 switch depth (convention: 6m, even though strict MOD is ~5.9m)
    o2_switch = 6

    results = []
    for intermediate_o2 in range(35, 85, 5):
        switch_depth = calculate_deco_switch_depth(intermediate_o2, max_po2_deco)
        if switch_depth < o2_switch + 3:
            continue  # no point if switch is at or below O2 depth
        if switch_depth > depth:
            continue  # can't switch deeper than the dive

        deco_config = [
            (intermediate_o2, 0, switch_depth),
            (100, 0, o2_switch),
        ]

        try:
            summary = run_profile(
                depth, bottom_time,
                back_gas=_back_gas,
                deco_cylinders_config=deco_config,
                gf_low=_gf_low, gf_high=_gf_high,
            )
            total_time = summary.runtime + 1.0  # +1 for gas switch stop
            total_deco = summary.total_deco_time + 1.0  # +1 for gas switch stop

            results.append({
                'intermediate_o2': intermediate_o2,
                'switch_depth': switch_depth,
                'o2_switch_depth': o2_switch,
                'total_time': total_time,
                'total_deco': total_deco,
            })
        except Exception:
            continue

    if not results:
        return None

    # Sort by total runtime
    results.sort(key=lambda r: r['total_time'])
    best = results[0]

    return {
        'back_gas': _back_gas,
        'best_intermediate': best['intermediate_o2'],
        'intermediate_switch': best['switch_depth'],
        'o2_switch': best['o2_switch_depth'],
        'total_time': best['total_time'],
        'total_deco': best['total_deco'],
        'all_results': results,
        'depth': depth,
        'bottom_time': bottom_time,
    }


def print_gas_optimization(depth, bottom_time, target_end=30,
                           max_po2_bottom=1.4, max_po2_deco=1.6,
                           back_gas=None):
    """Print best mix and optimized deco gases for a given depth/bottom time.

    Args:
        back_gas: (o2, he) tuple to fix the back gas blend. If None, calculates optimal.
    """
    mix = calculate_best_mix(depth, target_end, max_po2_bottom)
    _back_gas = back_gas if back_gas is not None else (mix['o2'], mix['he'])
    opt = optimize_deco_gases(depth, bottom_time, back_gas=_back_gas,
                              target_end=target_end,
                              max_po2_bottom=max_po2_bottom,
                              max_po2_deco=max_po2_deco)

    print(f"\n{'='*60}")
    print(f"  GAS OPTIMIZATION: {depth}m / {bottom_time} min | END <= {target_end}m")
    print(f"{'='*60}")
    if back_gas:
        # Show fixed gas info
        ambient_bar = SURFACE_PRESSURE + depth / 10.0
        po2 = ambient_bar * (back_gas[0] / 100.0)
        he_frac = back_gas[1] / 100.0
        end = (depth + 10) * (1 - he_frac) - 10
        print(f"\n  Fixed back gas:  Tx {back_gas[0]}/{back_gas[1]}")
        print(f"    PO2 at {depth}m: {po2:.2f} bar")
        print(f"    END: {end:.0f}m")
    else:
        print(f"\n  Best back gas:  Tx {mix['o2']}/{mix['he']}")
        print(f"    O2: {mix['o2']}%  He: {mix['he']}%  N2: {mix['n2']}%")
        print(f"    PO2 at {depth}m: {mix['po2_at_depth']:.2f} bar")
        print(f"    END: {mix['end']:.0f}m")

    if opt:
        print(f"\n  Optimal deco gases:")
        print(f"    Intermediate: EAN{opt['best_intermediate']} @ {opt['intermediate_switch']}m")
        print(f"    Shallow:      O2 @ {opt['o2_switch']}m")
        print(f"    Total deco:   {opt['total_deco']:.0f} min")
        print(f"    Total runtime: {opt['total_time']:.1f} min")

        print(f"\n  All intermediate options tested:")
        print(f"    {'Gas':<8} {'Switch':>7} {'Deco':>7} {'Runtime':>8}")
        print(f"    {'-'*8} {'-'*7} {'-'*7} {'-'*8}")
        for r in opt['all_results']:
            marker = " ◄" if r['intermediate_o2'] == opt['best_intermediate'] else ""
            print(f"    EAN{r['intermediate_o2']:<4} {r['switch_depth']:>5}m"
                  f" {r['total_deco']:>5.0f}m {r['total_time']:>7.1f}m{marker}")
    print()


def find_max_bottom_time(depth, back_gas=None, gas_rule='double_ascent',
                        back_gas_pressure=None, deco_50_pressure=None,
                        deco_o2_pressure=None,
                        gf_low=None, gf_high=None, descent_rate=None,
                        ascent_rate=None, sac_bottom=None, sac_deco=None):
    """
    Find the maximum bottom time satisfying the gas rule.

    gas_rule='double_ascent': all contingency scenarios (T+3 @ D+3, lost deco gas)
        must have non-negative back gas remaining within the fill pressure.
        The binding constraint is the worst-case scenario in the planning table.
    gas_rule='thirds': bar_at_turn >= 2/3 of fill pressure
    back_gas_pressure: override fill pressure (default: BACK_GAS_PRESSURE)
    deco_50_pressure: override fill pressure for EAN50 (default: DECO_50_PRESSURE)
    deco_o2_pressure: override fill pressure for O2 (default: DECO_O2_PRESSURE)
    Uses binary search over bottom time.
    """
    _back_gas = back_gas if back_gas is not None else BACK_GAS
    _back_gas_pressure = back_gas_pressure if back_gas_pressure is not None else BACK_GAS_PRESSURE
    _deco_50_pressure = deco_50_pressure if deco_50_pressure is not None else DECO_50_PRESSURE
    _deco_o2_pressure = deco_o2_pressure if deco_o2_pressure is not None else DECO_O2_PRESSURE
    _gf_low = gf_low if gf_low is not None else GF_LOW
    _gf_high = gf_high if gf_high is not None else GF_HIGH
    _descent_rate = descent_rate if descent_rate is not None else DESCENT_RATE
    _ascent_rate = ascent_rate if ascent_rate is not None else ASCENT_RATE
    _sac_bottom = sac_bottom if sac_bottom is not None else SAC_BOTTOM
    _sac_deco = sac_deco if sac_deco is not None else SAC_DECO
    thirds_pressure = _back_gas_pressure * 2 / 3

    lo, hi = 1, 120
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            if gas_rule == 'double_ascent':
                # Check all contingency scenarios fit within cylinder capacity
                # Worst cases: T+3 @ D+3 with lost EAN50 or lost O2
                scenarios = [
                    (depth, mid, False),
                    (depth, mid + 3, False),
                    (depth + 3, mid, False),
                    (depth + 3, mid + 3, False),
                    (depth, mid, 'ean50'),
                    (depth, mid, 'o2'),
                    (depth + 3, mid + 3, 'ean50'),
                    (depth + 3, mid + 3, 'o2'),
                ]
                ok = True
                for d, bt, lost in scenarios:
                    r = run_scenario("test", d, bt, deco_gases_lost=lost,
                                     back_gas=_back_gas,
                                     back_gas_pressure=_back_gas_pressure,
                                     deco_50_pressure=_deco_50_pressure,
                                     deco_o2_pressure=_deco_o2_pressure,
                                     gf_low=_gf_low, gf_high=_gf_high,
                                     descent_rate=_descent_rate, ascent_rate=_ascent_rate,
                                     sac_bottom=_sac_bottom, sac_deco=_sac_deco)
                    if r['back_remaining_bar'] < 0:
                        ok = False
                        break
                    if lost not in (True, 'ean50') and r['ean50_remaining_bar'] < 0:
                        ok = False
                        break
                    if lost not in (True, 'o2') and r['o2_remaining_bar'] < 0:
                        ok = False
                        break
            else:
                r = run_scenario("test", depth, mid, deco_gases_lost=False,
                                 back_gas=_back_gas,
                                 back_gas_pressure=_back_gas_pressure,
                                 deco_50_pressure=_deco_50_pressure,
                                 deco_o2_pressure=_deco_o2_pressure,
                                 gf_low=_gf_low, gf_high=_gf_high,
                                 descent_rate=_descent_rate, ascent_rate=_ascent_rate,
                                 sac_bottom=_sac_bottom, sac_deco=_sac_deco)
                ok = r['min_gas']['bar_at_turn'] >= thirds_pressure
            if ok:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1
        except Exception:
            hi = mid - 1
    return best


def generate_planning_table(depth, back_gas=None, bottom_time=None,
                            max_po2_deco=1.6, target_end=30,
                            back_gas_pressure=None, deco_50_pressure=None,
                            deco_o2_pressure=None,
                            gf_low=None, gf_high=None,
                            descent_rate=None, ascent_rate=None,
                            sac_bottom=None, sac_deco=None,
                            descent_stop_depth=None, descent_stop_time=5.0,
                            csv_path=None):
    """
    Generate a complete planning table for a given depth.

    Finds max bottom time T (rule of thirds), then produces scenarios:
    - D, T (main plan)
    - D, T+3
    - D+3, T
    - D+3, T+3
    - D, T no 50%
    - D, T no O2
    - D+3, T+3 no 50%
    - D+3, T+3 no O2
    - Bounce (5 min at D)

    Prints the table and minimum fills.
    """
    _back_gas = back_gas if back_gas is not None else BACK_GAS
    _back_gas_pressure = back_gas_pressure if back_gas_pressure is not None else BACK_GAS_PRESSURE
    _deco_50_pressure = deco_50_pressure if deco_50_pressure is not None else DECO_50_PRESSURE
    _deco_o2_pressure = deco_o2_pressure if deco_o2_pressure is not None else DECO_O2_PRESSURE
    _gf_low = gf_low if gf_low is not None else GF_LOW
    _gf_high = gf_high if gf_high is not None else GF_HIGH
    _descent_rate = descent_rate if descent_rate is not None else DESCENT_RATE
    _ascent_rate = ascent_rate if ascent_rate is not None else ASCENT_RATE
    _sac_bottom = sac_bottom if sac_bottom is not None else SAC_BOTTOM
    _sac_deco = sac_deco if sac_deco is not None else SAC_DECO
    _descent_stops = [(float(descent_stop_depth), float(descent_stop_time))] if descent_stop_depth is not None else None

    cfg = {
        'gf_low': _gf_low, 'gf_high': _gf_high,
        'descent_rate': _descent_rate, 'ascent_rate': _ascent_rate,
        'sac_bottom': _sac_bottom, 'sac_deco': _sac_deco,
    }

    # Find max bottom time if not specified
    if bottom_time is None:
        T = find_max_bottom_time(depth, _back_gas, back_gas_pressure=_back_gas_pressure,
                                 deco_50_pressure=_deco_50_pressure,
                                 deco_o2_pressure=_deco_o2_pressure,
                                 gf_low=_gf_low, gf_high=_gf_high,
                                 descent_rate=_descent_rate, ascent_rate=_ascent_rate,
                                 sac_bottom=_sac_bottom, sac_deco=_sac_deco)
    else:
        T = bottom_time
    D = depth

    print(f"\n{'='*70}")
    print(f"  PLANNING TABLE: {D}m | Tx {_back_gas[0]}/{_back_gas[1]} | ZHL-16C-GF {_gf_low*100:.0f}/{_gf_high*100:.0f}")
    print(f"  Max bottom time (double ascent): {T}'")
    print(f"{'='*70}\n")

    # Define scenarios
    scenarios = [
        (D,   T,   False, "Main"),
        (D,   T+3, False, "Longer"),
        (D+3, T,   False, "Deeper"),
        (D+3, T+3, False, "D & L"),
        (D,   T,   'ean50', "no 50"),
        (D,   T,   'o2', "no O2"),
        (D+3, T+3, 'ean50', "no 50"),
        (D+3, T+3, 'o2', "no O2"),
        (D,   10, False, "bounce"),
    ]

    results = []
    for d, bt, lost, tag in scenarios:
        name = f"{bt}@{d}" + (f" {tag}" if tag else "")
        r = run_scenario(name, d, bt, deco_gases_lost=lost,
                         back_gas=_back_gas,
                         back_gas_pressure=_back_gas_pressure,
                         deco_50_pressure=_deco_50_pressure,
                         deco_o2_pressure=_deco_o2_pressure,
                         gf_low=_gf_low, gf_high=_gf_high,
                         descent_rate=_descent_rate, ascent_rate=_ascent_rate,
                         sac_bottom=_sac_bottom, sac_deco=_sac_deco,
                         descent_stops=_descent_stops)
        r['leave_time'] = bt
        results.append(r)

    from tabulate import tabulate

    # Three-line headers: leave_time / depth / description
    col_headers = ["\n\n"]
    for r, (d, bt, lost, tag) in zip(results, scenarios):
        line2 = f"{d}m"
        line3 = tag
        if tag == "bounce":
            col_headers.append(f"\n{line2}\n{line3}")
        else:
            line1 = f"{r['leave_time']}'"
            col_headers.append(f"{line1}\n{line2}\n{line3}")

    # Build rows
    rows = []

    # Depth rows showing runtime when leaving bottom
    depth_set = sorted(set(r['depth'] for r in results), reverse=True)
    for dd in depth_set:
        row = [f"{int(dd)}m"]
        for r in results:
            if r['depth'] == dd:
                row.append(f"{r['bottom_time']}")
            else:
                row.append("-")
        rows.append(row)

    # Deco stop rows (prefix with gas marker: - for EAN50, * for O2)
    all_stop_depths = sorted(
        set(d for r in results for d, t in r['deco_stops']), reverse=True
    )
    for sd in all_stop_depths:
        # Determine gas at this stop depth
        if sd <= _DECO_O2_SWITCH_DEPTH:
            gas_mark = "*"
        elif sd <= _DECO_50_SWITCH_DEPTH:
            gas_mark = "-"
        else:
            gas_mark = " "
        row = [f"{gas_mark}{int(sd)}m"]
        for r in results:
            stop_time = next((t for dp, t in r['deco_stops'] if dp == sd), None)
            if stop_time is None:
                # Check if this gas was lost for this scenario
                if sd <= _DECO_O2_SWITCH_DEPTH and r.get('deco_gases_lost') in (True, 'o2'):
                    row.append("-")
                elif _DECO_O2_SWITCH_DEPTH < sd <= _DECO_50_SWITCH_DEPTH and r.get('deco_gases_lost') in (True, 'ean50'):
                    row.append("-")
                else:
                    row.append("-")
            else:
                rt_info = r['stop_runtimes'].get(sd)
                if rt_info is not None:
                    row.append(f"{rt_info:.0f} ({stop_time:.0f})")
                else:
                    row.append(f"({stop_time:.0f})")
        rows.append(row)

    rows.append(["*0m"] + [f"{r['total_time']:.0f}" for r in results])
    rows.append(["---"] + ["---"] * len(results))

    # Summary rows at bottom
    rows.append(["Depth"] + [r['depth'] for r in results])
    rows.append(["Total deco"] + [f"{r['total_deco']:.0f}" for r in results])
    rows.append(["Runtime"] + [f"{r['total_time']:.0f}" for r in results])
    rows.append(["Turn pressure"] + [f"{r['min_gas']['bar_at_turn']:.0f}" for r in results])
    rows.append(["---"] + ["---"] * len(results))
    rows.append(["OTU"] + [f"{r['otu']:.0f}" for r in results])
    rows.append(["CNS %"] + [f"{r['cns']:.0f}%" for r in results])
    rows.append(["END"] + [f"{(r['depth']+10)*(1-_back_gas[1]/100)-10:.0f}m" for r in results])
    rows.append(["PO2"] + [f"{(SURFACE_PRESSURE + r['depth']/10)*(_back_gas[0]/100):.2f}" for r in results])
    rows.append(["Gas density g/L"] + [f"{_gas_density_gl(_back_gas[0], _back_gas[1], r['depth']):.2f}" for r in results])
    rows.append(["---"] + ["---"] * len(results))

    # End gas remaining
    rows.append(["Back gas left"] + [f"{r['back_remaining_bar']:.0f}" for r in results])
    ean50_row = ["EAN50"]
    for r in results:
        if r['deco_gases_lost'] in (True, 'ean50'):
            ean50_row.append("--")
        else:
            ean50_row.append(f"{r['ean50_remaining_bar']:.0f}")
    rows.append(ean50_row)
    o2_row = ["O2"]
    for r in results:
        if r['deco_gases_lost'] in (True, 'o2'):
            o2_row.append("--")
        else:
            o2_row.append(f"{r['o2_remaining_bar']:.0f}")
    rows.append(o2_row)

    print(tabulate(rows, headers=col_headers, tablefmt="simple", colalign=("left",) + ("right",) * len(results)))

    # Minimum fills: worst case usage for each cylinder across all scenarios
    max_back_litres = 0
    max_50_litres = 0
    max_o2_litres = 0
    for r in results:
        back_used_bar = _back_gas_pressure - r['back_remaining_bar']
        back_used_l = back_used_bar * BACK_GAS_VOL
        if back_used_l > max_back_litres:
            max_back_litres = back_used_l
        if r['deco_gases_lost'] not in (True, 'ean50'):
            e50_used_bar = _deco_50_pressure - r['ean50_remaining_bar']
            e50_used_l = e50_used_bar * DECO_50_VOL
            if e50_used_l > max_50_litres:
                max_50_litres = e50_used_l
        if r['deco_gases_lost'] not in (True, 'o2'):
            o2_used_bar = _deco_o2_pressure - r['o2_remaining_bar']
            o2_used_l = o2_used_bar * DECO_O2_VOL
            if o2_used_l > max_o2_litres:
                max_o2_litres = o2_used_l

    max_back_bar = max_back_litres / BACK_GAS_VOL
    deco_cyls = [(11.1, "11.1L"), (10.3, "10.3L"), (5.7, "5.7L")]

    def deco_fill_str(litres, name):
        bar_strs = [f"{litres/vol:.0f}bar {label}" for vol, label in deco_cyls]
        return f"    {name}: {litres:.0f}L ({', '.join(bar_strs)})"

    print(f"\n  MINIMUM FILLS (worst case):")
    print(f"    Back gas Tx {_back_gas[0]}/{_back_gas[1]}: {max_back_litres:.0f}L ({max_back_bar:.0f} bar)")
    print(deco_fill_str(max_50_litres, "EAN50"))
    print(deco_fill_str(max_o2_litres, "O2"))

    print(f"\n  ASSUMPTIONS:")
    print(f"    SAC: {_sac_bottom} L/min (bottom), {_sac_deco} L/min (deco)")
    print(f"    Descent: {_descent_rate} m/min, Ascent: {_ascent_rate} m/min")
    if _descent_stops:
        for ds_depth, ds_time in _descent_stops:
            print(f"    Descent stop: {ds_time:.0f} min @ {ds_depth:.0f}m (S-drill)")
    print(f"    Cylinders: back {BACK_GAS_VOL}L @ {_back_gas_pressure} bar, "
          f"EAN50 {DECO_50_VOL}L @ {_deco_50_pressure} bar, "
          f"O2 {DECO_O2_VOL}L @ {_deco_o2_pressure} bar")
    print(f"    Deco switches: EAN50 @ {_DECO_50_SWITCH_DEPTH}m, O2 @ {_DECO_O2_SWITCH_DEPTH}m")
    print(f"    Last stop: 3m (deco stops) / {_DECO_O2_SWITCH_DEPTH}m (O2 switch)")
    print(f"    Min gas: 2-diver, 1 min problem-solving at depth")
    hot_factor = (273.15 + FILL_TEMP_C) / (273.15 + WATER_TEMP_C)
    print(f"    Hot fill ({FILL_TEMP_C}degC -> {WATER_TEMP_C}degC): "
          f"back {_back_gas_pressure * hot_factor:.0f} bar, "
          f"EAN50 {_deco_50_pressure * hot_factor:.0f} bar, "
          f"O2 {_deco_o2_pressure * hot_factor:.0f} bar")
    print()

    if csv_path is not None:
        import csv as _csv
        csv_rows = []
        csv_rows.append([f"PLANNING TABLE: {D}m | Tx {_back_gas[0]}/{_back_gas[1]} | ZHL-16C-GF {_gf_low*100:.0f}/{_gf_high*100:.0f}"])
        csv_rows.append([f"Max bottom time (double ascent): {T}'"])
        csv_rows.append([])
        csv_rows.append([""] + [f"{r['leave_time']}'" if tag != "bounce" else "" for r, (_, _, _, tag) in zip(results, scenarios)])
        csv_rows.append([""] + [f"{d}m" for d, _, _, _ in scenarios])
        csv_rows.append([""] + [tag for _, _, _, tag in scenarios])
        csv_rows.append([])
        depth_set_csv = sorted(set(r['depth'] for r in results), reverse=True)
        for dd in depth_set_csv:
            row = [f"{int(dd)}m"]
            for r in results:
                row.append(r['bottom_time'] if r['depth'] == dd else "")
            csv_rows.append(row)
        all_stop_depths_csv = sorted(
            set(d for r in results for d, t in r['deco_stops']), reverse=True
        )
        for sd in all_stop_depths_csv:
            if sd <= _DECO_O2_SWITCH_DEPTH:
                label = f"*{int(sd)}m"
            elif sd <= _DECO_50_SWITCH_DEPTH:
                label = f"-{int(sd)}m"
            else:
                label = f"{int(sd)}m"
            row = [label]
            for r in results:
                stop_time = next((t for dp, t in r['deco_stops'] if dp == sd), None)
                if stop_time is None:
                    row.append("")
                else:
                    rt_info = r['stop_runtimes'].get(sd)
                    if rt_info is not None:
                        row.append(f"{rt_info:.0f} ({stop_time:.0f})")
                    else:
                        row.append(f"({stop_time:.0f})")
            csv_rows.append(row)
        csv_rows.append(["*0m"] + [f"{r['total_time']:.0f}" for r in results])
        csv_rows.append([])
        csv_rows.append(["Depth"] + [r['depth'] for r in results])
        csv_rows.append(["Total deco"] + [f"{r['total_deco']:.0f}" for r in results])
        csv_rows.append(["Runtime"] + [f"{r['total_time']:.0f}" for r in results])
        csv_rows.append(["Turn pressure"] + [f"{r['min_gas']['bar_at_turn']:.0f}" for r in results])
        csv_rows.append([])
        csv_rows.append(["OTU"] + [f"{r['otu']:.0f}" for r in results])
        csv_rows.append(["CNS %"] + [f"{r['cns']:.0f}%" for r in results])
        csv_rows.append(["END"] + [f"{(r['depth']+10)*(1-_back_gas[1]/100)-10:.0f}m" for r in results])
        csv_rows.append(["PO2"] + [f"{(SURFACE_PRESSURE + r['depth']/10)*(_back_gas[0]/100):.2f}" for r in results])
        csv_rows.append(["Gas density g/L"] + [f"{_gas_density_gl(_back_gas[0], _back_gas[1], r['depth']):.2f}" for r in results])
        csv_rows.append([])
        csv_rows.append(["Back gas left"] + [f"{r['back_remaining_bar']:.0f}" for r in results])
        csv_rows.append(["EAN50"] + [
            "--" if r['deco_gases_lost'] in (True, 'ean50') else f"{r['ean50_remaining_bar']:.0f}"
            for r in results])
        csv_rows.append(["O2"] + [
            "--" if r['deco_gases_lost'] in (True, 'o2') else f"{r['o2_remaining_bar']:.0f}"
            for r in results])
        csv_rows.append([])
        max_back_litres_csv = max(
            (_back_gas_pressure - r['back_remaining_bar']) * BACK_GAS_VOL for r in results)
        max_50_litres_csv = max(
            (_deco_50_pressure - r['ean50_remaining_bar']) * DECO_50_VOL
            for r in results if r['deco_gases_lost'] not in (True, 'ean50'))
        max_o2_litres_csv = max(
            (_deco_o2_pressure - r['o2_remaining_bar']) * DECO_O2_VOL
            for r in results if r['deco_gases_lost'] not in (True, 'o2'))
        csv_rows.append(["MIN FILLS"])
        csv_rows.append([f"Back gas Tx {_back_gas[0]}/{_back_gas[1]}",
                         f"{max_back_litres_csv:.0f}L",
                         f"{max_back_litres_csv / BACK_GAS_VOL:.0f} bar"])
        csv_rows.append(["EAN50", f"{max_50_litres_csv:.0f}L",
                         f"{max_50_litres_csv/11.1:.0f}bar 11.1L",
                         f"{max_50_litres_csv/10.3:.0f}bar 10.3L",
                         f"{max_50_litres_csv/5.7:.0f}bar 5.7L"])
        csv_rows.append(["O2", f"{max_o2_litres_csv:.0f}L",
                         f"{max_o2_litres_csv/11.1:.0f}bar 11.1L",
                         f"{max_o2_litres_csv/10.3:.0f}bar 10.3L",
                         f"{max_o2_litres_csv/5.7:.0f}bar 5.7L"])
        csv_rows.append([])
        csv_rows.append(["ASSUMPTIONS"])
        csv_rows.append(["SAC", f"{_sac_bottom} L/min (bottom)", f"{_sac_deco} L/min (deco)"])
        csv_rows.append(["Descent", f"{_descent_rate} m/min"])
        csv_rows.append(["Ascent", f"{_ascent_rate} m/min"])
        if _descent_stops:
            for ds_depth, ds_time in _descent_stops:
                csv_rows.append(["Descent stop", f"{ds_time:.0f} min @ {ds_depth:.0f}m (S-drill)"])
        csv_rows.append(["Cylinders",
                         f"back {BACK_GAS_VOL}L @ {_back_gas_pressure} bar",
                         f"EAN50 {DECO_50_VOL}L @ {_deco_50_pressure} bar",
                         f"O2 {DECO_O2_VOL}L @ {_deco_o2_pressure} bar"])
        csv_rows.append(["Deco switches", f"EAN50 @ {_DECO_50_SWITCH_DEPTH}m", f"O2 @ {_DECO_O2_SWITCH_DEPTH}m"])
        csv_rows.append(["Last stop", "3m (deco stops)", f"{_DECO_O2_SWITCH_DEPTH}m (O2 switch)"])
        csv_rows.append(["Min gas", "2-diver", "1 min problem-solving at depth"])
        hot_factor_csv = (273.15 + FILL_TEMP_C) / (273.15 + WATER_TEMP_C)
        csv_rows.append([f"Hot fill ({FILL_TEMP_C}degC -> {WATER_TEMP_C}degC)",
                         f"back {_back_gas_pressure * hot_factor_csv:.0f} bar",
                         f"EAN50 {_deco_50_pressure * hot_factor_csv:.0f} bar",
                         f"O2 {_deco_o2_pressure * hot_factor_csv:.0f} bar"])
        filename = csv_path if csv_path is not True else f"plan_{D}m_Tx{_back_gas[0]}_{_back_gas[1]}.csv"
        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            _csv.writer(f).writerows(csv_rows)
        print(f"  Exported: {filename}")

    return results



def generate_all_plans():
    """Generate planning tables for multiple depths with best mix, export to CSV."""
    plans = [
        (40, None, 30),    # best mix for END 30
        (45, (22, 27), None),  # fixed mix - already filled
        (50, None, 30),    # best mix for END 30
        (55, None, 30),    # best mix for END 30
        (60, None, 30),    # best mix for END 30
    ]

    print("=" * 70)
    print("  GENERATING PLANNING TABLES")
    print("=" * 70)

    for depth, fixed_gas, target_end in plans:
        if fixed_gas:
            back_gas = fixed_gas
            print(f"\n  {depth}m: Using fixed Tx {back_gas[0]}/{back_gas[1]}")
        else:
            mix = calculate_best_mix(depth, target_end=target_end)
            back_gas = (mix['o2'], mix['he'])
            print(f"\n  {depth}m: Best mix Tx {mix['o2']}/{mix['he']} "
                  f"(END={mix['end']:.0f}m, PO2={mix['po2_at_depth']:.2f})")

        generate_planning_table(depth, back_gas=back_gas, csv_path=True)

    print(f"\n{'=' * 70}")
    print("  All plans exported to CSV files.")
    print("=" * 70)


def main():
    print("Dive Plan - Trimix 23/25 | GF 50/70")
    print(f"Back gas: {BACK_GAS_VOL}L @ {BACK_GAS_PRESSURE} bar | "
          f"EAN50: {DECO_50_VOL}L @ {DECO_50_PRESSURE} bar | "
          f"O2: {DECO_O2_VOL}L @ {DECO_O2_PRESSURE} bar")
    print(f"Descent: {DESCENT_RATE} m/min | Ascent: {ASCENT_RATE} m/min")
    print(f"SAC: {SAC_BOTTOM} L/min (bottom) / {SAC_DECO} L/min (deco)")
    print()

    scenarios = [
        ("27@45", 45, 27, False),
        ("30@45", 45, 30, False),
        ("27@48", 48, 27, False),
        ("30@48", 48, 30, False),
        ("10@45", 45, 10, False),
        ("27@45\nno 50", 45, 27, 'ean50'),
        ("30@45\nno 50", 45, 30, 'ean50'),
        ("27@48\nno 50", 48, 27, 'ean50'),
        ("30@48\nno 50", 48, 30, 'ean50'),
        ("27@45\nno O2", 45, 27, 'o2'),
        ("30@45\nno O2", 45, 30, 'o2'),
        ("27@48\nno O2", 48, 27, 'o2'),
        ("30@48\nno O2", 48, 30, 'o2'),
        ("27@45\nno deco", 45, 27, True),
        ("10@45\nturn", 45, 10, False),
    ]

    results = []
    for name, depth, bt, lost in scenarios:
        r = run_scenario(name, depth, bt, deco_gases_lost=lost)
        results.append(r)

    print_table(results)
    plot_profiles(results)

    # Gas optimization for the main dive depths
    for depth in [45, 48]:
        print_gas_optimization(depth, 27, target_end=30)


if __name__ == '__main__':
    main()
