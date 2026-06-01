"""Dive planner web interface."""
import io
import csv as _csv
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dive_plan import (  # noqa: E402
    ASCENT_RATE,
    BACK_GAS,
    BACK_GAS_PRESSURE,
    BACK_GAS_VOL,
    DECO_50_PRESSURE,
    DECO_50_VOL,
    DECO_O2_PRESSURE,
    DECO_O2_VOL,
    DESCENT_RATE,
    FILL_TEMP_C,
    GF_HIGH,
    GF_LOW,
    SAC_BOTTOM,
    SAC_DECO,
    SURFACE_PRESSURE,
    WATER_TEMP_C,
    _DECO_50_SWITCH_DEPTH,
    _DECO_O2_SWITCH_DEPTH,
    _gas_density_gl,
    find_max_bottom_time,
    run_scenario,
)

st.set_page_config(
    page_title="Dive Planner",
    page_icon="🤿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Sidebar inputs ───────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🤿 Dive Planner")

    st.subheader("Gas")
    col1, col2 = st.columns(2)
    o2 = col1.number_input("O2%", min_value=18, max_value=40, value=22, step=1)
    he = col2.number_input("He%", min_value=0, max_value=60, value=27, step=1)
    back_gas = (int(o2), int(he))

    st.subheader("Depth & Time")
    depth = int(st.number_input("Depth (m)", min_value=10, max_value=80, value=48, step=1))
    auto_time = st.checkbox("Auto bottom time", value=True,
                            help="Find max safe bottom time by rule of thirds")
    manual_bt_val = None
    if not auto_time:
        manual_bt_val = int(st.number_input("Bottom time (min)", min_value=5, max_value=120, value=31, step=1))

    st.subheader("Cylinders")
    col1, col2, col3 = st.columns(3)
    back_gas_pressure = int(col1.number_input("Back (bar)", min_value=150, max_value=300, value=230, step=5))
    deco_50_pressure = int(col2.number_input("EAN50 (bar)", min_value=100, max_value=250, value=200, step=5))
    deco_o2_pressure = int(col3.number_input("O2 (bar)", min_value=100, max_value=250, value=200, step=5))

    st.subheader("Deco Model")
    col1, col2 = st.columns(2)
    gf_low = col1.number_input("GF low %", min_value=10, max_value=100, value=50, step=5) / 100
    gf_high = col2.number_input("GF high %", min_value=10, max_value=100, value=80, step=5) / 100

    st.subheader("Rates")
    col1, col2 = st.columns(2)
    descent_rate = int(col1.number_input("Descent (m/min)", min_value=5, max_value=40, value=20, step=1))
    ascent_rate = int(col2.number_input("Ascent (m/min)", min_value=3, max_value=20, value=10, step=1))

    st.subheader("Descent Stop (S-drill)")
    enable_stop = st.checkbox("Enable S-drill stop")
    descent_stops_tuple = None
    if enable_stop:
        col1, col2 = st.columns(2)
        s_depth = int(col1.number_input("Depth (m)", min_value=3, max_value=20, value=5, step=1))
        s_time = int(col2.number_input("Duration (min)", min_value=1, max_value=30, value=5, step=1))
        descent_stops_tuple = ((s_depth, s_time),)

    st.subheader("Gas Consumption")
    col1, col2 = st.columns(2)
    sac_bottom = int(col1.number_input("SAC bottom (L/min)", min_value=10, max_value=40, value=20, step=1))
    sac_deco = int(col2.number_input("SAC deco (L/min)", min_value=10, max_value=30, value=17, step=1))


# ─── Compute ──────────────────────────────────────────────────────────────────
@st.cache_data
def _get_max_time(depth, back_gas, bgp, d50p, do2p, gfl, gfh, dr, ar, sb, sd):
    return find_max_bottom_time(
        depth, back_gas,
        back_gas_pressure=bgp, deco_50_pressure=d50p, deco_o2_pressure=do2p,
        gf_low=gfl, gf_high=gfh, descent_rate=dr, ascent_rate=ar,
        sac_bottom=sb, sac_deco=sd,
    )


@st.cache_data
def _compute_scenarios(back_gas, depth, T, bgp, d50p, do2p, gfl, gfh, dr, ar, sb, sd, dst):
    D = depth
    descent_stops = list(dst) if dst else None
    scenario_defs = [
        (D,     T,      False,    "Main"),
        (D,     T + 3,  False,    "Longer"),
        (D + 3, T,      False,    "Deeper"),
        (D + 3, T + 3,  False,    "D & L"),
        (D,     T,      "ean50",  "no 50%"),
        (D,     T,      "o2",     "no O2"),
        (D + 3, T + 3,  "ean50",  "no 50% (D)"),
        (D + 3, T + 3,  "o2",     "no O2 (D)"),
        (D,     10,     False,    "Bounce"),
    ]
    results = []
    for d, bt, lost, tag in scenario_defs:
        r = run_scenario(
            tag, d, bt, deco_gases_lost=lost,
            back_gas=back_gas,
            back_gas_pressure=bgp, deco_50_pressure=d50p, deco_o2_pressure=do2p,
            gf_low=gfl, gf_high=gfh,
            descent_rate=dr, ascent_rate=ar,
            sac_bottom=sb, sac_deco=sd,
            descent_stops=descent_stops,
        )
        r["leave_time"] = bt
        r["tag"] = tag
        results.append(r)
    return results, scenario_defs


with st.spinner("Computing…"):
    T = (
        _get_max_time(depth, back_gas, back_gas_pressure, deco_50_pressure, deco_o2_pressure,
                      gf_low, gf_high, descent_rate, ascent_rate, sac_bottom, sac_deco)
        if auto_time else manual_bt_val
    )
    results, scenario_defs = _compute_scenarios(
        back_gas, depth, T,
        back_gas_pressure, deco_50_pressure, deco_o2_pressure,
        gf_low, gf_high, descent_rate, ascent_rate, sac_bottom, sac_deco,
        descent_stops_tuple,
    )

# ─── Header ───────────────────────────────────────────────────────────────────
st.title(f"🤿 {depth}m | Tx {o2}/{he} | GF {int(gf_low*100)}/{int(gf_high*100)}")
st.caption(
    f"Max bottom time: **{T}'** | Descent: {descent_rate} m/min | "
    f"Ascent: {ascent_rate} m/min | SAC: {sac_bottom}/{sac_deco} L/min"
)

# ─── Scenario selector ────────────────────────────────────────────────────────
tags = [r["tag"] for r in results]
selected_tag = st.radio(
    "Scenario (controls ceiling band + gas chart):",
    tags, horizontal=True, index=0,
)
sel = next(r for r in results if r["tag"] == selected_tag)

# ─── Planning table ───────────────────────────────────────────────────────────
st.subheader("Planning Table")

# Build header row
col_labels = [f"{r['leave_time']}'\n{r['depth']}m\n{r['tag']}" for r in results]

# Determine all deco stop depths across all scenarios
all_stop_depths = sorted(
    {d for r in results for d, t in r["deco_stops"]}, reverse=True
)

# Determine depth rows
depth_set = sorted({r["depth"] for r in results}, reverse=True)

table_rows = {}

# Depth rows (leave time)
for dd in depth_set:
    row = []
    for r in results:
        row.append(str(r["bottom_time"]) if r["depth"] == dd else "")
    table_rows[f"{int(dd)}m"] = row

# Deco stop rows
for sd in all_stop_depths:
    if sd <= _DECO_O2_SWITCH_DEPTH:
        label = f"*{int(sd)}m"
    elif sd <= _DECO_50_SWITCH_DEPTH:
        label = f"-{int(sd)}m"
    else:
        label = f" {int(sd)}m"
    row = []
    for r in results:
        st_val = next((t for dp, t in r["deco_stops"] if dp == sd), None)
        if st_val is None:
            row.append("")
        else:
            rt = r["stop_runtimes"].get(sd)
            row.append(f"{rt:.0f} ({st_val:.0f})" if rt is not None else f"({st_val:.0f})")
    table_rows[label] = row

# Total time row
table_rows["*0m"] = [f"{r['total_time']:.0f}" for r in results]
table_rows["---"] = ["---"] * len(results)
table_rows["Total deco"] = [f"{r['total_deco']:.0f}" for r in results]
table_rows["Runtime"] = [f"{r['total_time']:.0f}" for r in results]
table_rows["Turn pressure"] = [f"{r['min_gas']['bar_at_turn']:.0f}" for r in results]
table_rows["---2"] = ["---"] * len(results)
table_rows["OTU"] = [f"{r['otu']:.0f}" for r in results]
table_rows["CNS %"] = [f"{r['cns']:.0f}%" for r in results]
table_rows["END"] = [f"{(r['depth']+10)*(1-back_gas[1]/100)-10:.0f}m" for r in results]
table_rows["PO2"] = [f"{(SURFACE_PRESSURE + r['depth']/10)*(back_gas[0]/100):.2f}" for r in results]
table_rows["Gas density"] = [f"{_gas_density_gl(back_gas[0], back_gas[1], r['depth']):.2f} g/L" for r in results]
table_rows["---3"] = ["---"] * len(results)
table_rows["Back gas left"] = [f"{r['back_remaining_bar']:.0f} bar" for r in results]
table_rows["EAN50"] = [
    "--" if r["deco_gases_lost"] in (True, "ean50") else f"{r['ean50_remaining_bar']:.0f} bar"
    for r in results
]
table_rows["O2"] = [
    "--" if r["deco_gases_lost"] in (True, "o2") else f"{r['o2_remaining_bar']:.0f} bar"
    for r in results
]

df = pd.DataFrame(table_rows, index=col_labels).T
df.index.name = ""

st.dataframe(df, use_container_width=True)

# ─── Charts ───────────────────────────────────────────────────────────────────
st.subheader("Dive Profiles")

COLORS = [
    "#4c9be8",  # Main - blue
    "#56b84b",  # Longer - green
    "#f0922b",  # Deeper - orange
    "#ae79d4",  # D & L - purple
    "#e377c2",  # no 50% - pink
    "#d62728",  # no O2 - red
    "#f7b6d2",  # no 50% (D) - light pink
    "#ff9896",  # no O2 (D) - light red
    "#8c8c8c",  # Bounce - grey
]


def _hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    subplot_titles=("Depth Profile", "Gas Pressure"),
    vertical_spacing=0.08,
    row_heights=[0.6, 0.4],
)

# ── Depth profile traces ──────────────────────────────────────────────────────
for i, r in enumerate(results):
    is_sel = r["tag"] == selected_tag
    color = COLORS[i]
    fig.add_trace(
        go.Scatter(
            x=r["times"],
            y=r["depths"],
            mode="lines",
            name=r["tag"],
            line=dict(color=color, width=3 if is_sel else 1.5),
            opacity=1.0 if is_sel else 0.4,
            legendgroup=r["tag"],
            legendgrouptitle_text=None,
            showlegend=True,
            hovertemplate=(
                f"<b>{r['tag']}</b><br>"
                "T+%{x:.0f} min<br>"
                "Depth: %{y:.0f}m<extra></extra>"
            ),
        ),
        row=1, col=1,
    )

# ── Ceiling band for selected scenario ───────────────────────────────────────
cp = sel.get("ceiling_profile", [])
if cp:
    cp_deco = [(t, d, c) for t, d, c in cp if c > 0.5]
    if cp_deco:
        t_vals = [t for t, d, c in cp_deco]
        d_vals = [d for t, d, c in cp_deco]
        c_vals = [c for t, d, c in cp_deco]
        sel_color = COLORS[tags.index(selected_tag)]

        fig.add_trace(
            go.Scatter(
                x=t_vals, y=c_vals,
                mode="lines",
                name=f"Ceiling ({selected_tag})",
                line=dict(color=sel_color, width=1.5, dash="dash"),
                legendgroup=selected_tag,
                showlegend=True,
                hovertemplate="Ceiling: %{y:.0f}m @ T+%{x:.0f}min<extra></extra>",
            ),
            row=1, col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=t_vals + t_vals[::-1],
                y=c_vals + d_vals[::-1],
                fill="toself",
                fillcolor=_hex_to_rgba(sel_color, 0.15),
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name="_ceiling_fill",
            ),
            row=1, col=1,
        )

# ── Gas switch depth markers ──────────────────────────────────────────────────
fig.add_hline(
    y=_DECO_50_SWITCH_DEPTH,
    line=dict(color="#56b84b", width=1, dash="dot"),
    annotation_text=f"EAN50 @ {_DECO_50_SWITCH_DEPTH}m",
    annotation_position="top right",
    row=1, col=1,
)
fig.add_hline(
    y=_DECO_O2_SWITCH_DEPTH,
    line=dict(color="#17becf", width=1, dash="dot"),
    annotation_text=f"O2 @ {_DECO_O2_SWITCH_DEPTH}m",
    annotation_position="top right",
    row=1, col=1,
)

# ── Gas pressure traces ───────────────────────────────────────────────────────
GAS_COLORS = {"back": "#4c9be8", "ean50": "#56b84b", "o2": "#17becf"}
GAS_LABELS = {"back": "Back gas", "ean50": "EAN50", "o2": "O2"}

gpp = sel.get("gas_pressure_profile", {})
for gas_key, color in GAS_COLORS.items():
    if gas_key not in gpp:
        continue
    pts = gpp[gas_key]
    fig.add_trace(
        go.Scatter(
            x=[t for t, p in pts],
            y=[p for t, p in pts],
            mode="lines",
            name=GAS_LABELS[gas_key],
            line=dict(color=color, width=2),
            legendgroup=f"gas_{gas_key}",
            showlegend=True,
            hovertemplate=f"<b>{GAS_LABELS[gas_key]}</b>: %{{y:.0f}} bar @ T+%{{x:.0f}}min<extra></extra>",
        ),
        row=2, col=1,
    )

# Turn pressure reference line
turn_p = sel["min_gas"]["bar_at_turn"]
fig.add_hline(
    y=turn_p,
    line=dict(color="#d62728", width=1, dash="dash"),
    annotation_text=f"Turn: {turn_p:.0f} bar",
    annotation_position="top right",
    row=2, col=1,
)

# ── Layout ────────────────────────────────────────────────────────────────────
fig.update_layout(
    height=680,
    template="plotly_dark",
    margin=dict(l=60, r=80, t=60, b=40),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    hovermode="x",
)
fig.update_yaxes(autorange="reversed", title_text="Depth (m)", row=1, col=1)
fig.update_yaxes(title_text="Pressure (bar)", rangemode="tozero", row=2, col=1)
fig.update_xaxes(title_text="Time (min)", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)

# ─── CSV download ─────────────────────────────────────────────────────────────
st.subheader("Export")


def _build_csv_bytes():
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([f"PLANNING TABLE: {depth}m | Tx {back_gas[0]}/{back_gas[1]} | ZHL-16C-GF {int(gf_low*100)}/{int(gf_high*100)}"])
    w.writerow([f"Max bottom time (double ascent): {T}'"])
    w.writerow([])
    w.writerow([""] + [f"{r['leave_time']}'" if r['tag'] != 'Bounce' else "" for r in results])
    w.writerow([""] + [f"{r['depth']}m" for r in results])
    w.writerow([""] + [r["tag"] for r in results])
    w.writerow([])
    for dd in sorted({r["depth"] for r in results}, reverse=True):
        w.writerow([f"{int(dd)}m"] + [str(r["bottom_time"]) if r["depth"] == dd else "" for r in results])
    for sd in sorted({d for r in results for d, t in r["deco_stops"]}, reverse=True):
        lbl = f"*{int(sd)}m" if sd <= _DECO_O2_SWITCH_DEPTH else (f"-{int(sd)}m" if sd <= _DECO_50_SWITCH_DEPTH else f"{int(sd)}m")
        row = [lbl]
        for r in results:
            st_val = next((t for dp, t in r["deco_stops"] if dp == sd), None)
            if st_val is None:
                row.append("")
            else:
                rt = r["stop_runtimes"].get(sd)
                row.append(f"{rt:.0f} ({st_val:.0f})" if rt is not None else f"({st_val:.0f})")
        w.writerow(row)
    w.writerow(["*0m"] + [f"{r['total_time']:.0f}" for r in results])
    w.writerow([])
    w.writerow(["Depth"] + [r["depth"] for r in results])
    w.writerow(["Total deco"] + [f"{r['total_deco']:.0f}" for r in results])
    w.writerow(["Runtime"] + [f"{r['total_time']:.0f}" for r in results])
    w.writerow(["Turn pressure"] + [f"{r['min_gas']['bar_at_turn']:.0f}" for r in results])
    w.writerow([])
    w.writerow(["OTU"] + [f"{r['otu']:.0f}" for r in results])
    w.writerow(["CNS %"] + [f"{r['cns']:.0f}%" for r in results])
    w.writerow(["END"] + [f"{(r['depth']+10)*(1-back_gas[1]/100)-10:.0f}m" for r in results])
    w.writerow(["PO2"] + [f"{(SURFACE_PRESSURE + r['depth']/10)*(back_gas[0]/100):.2f}" for r in results])
    w.writerow(["Gas density g/L"] + [f"{_gas_density_gl(back_gas[0], back_gas[1], r['depth']):.2f}" for r in results])
    w.writerow([])
    w.writerow(["Back gas left"] + [f"{r['back_remaining_bar']:.0f}" for r in results])
    w.writerow(["EAN50"] + ["--" if r["deco_gases_lost"] in (True, "ean50") else f"{r['ean50_remaining_bar']:.0f}" for r in results])
    w.writerow(["O2"] + ["--" if r["deco_gases_lost"] in (True, "o2") else f"{r['o2_remaining_bar']:.0f}" for r in results])
    w.writerow([])
    w.writerow(["ASSUMPTIONS"])
    w.writerow(["SAC", f"{sac_bottom} L/min (bottom)", f"{sac_deco} L/min (deco)"])
    w.writerow(["Descent", f"{descent_rate} m/min", f"Ascent {ascent_rate} m/min"])
    if descent_stops_tuple:
        for ds_d, ds_t in descent_stops_tuple:
            w.writerow(["Descent stop", f"{ds_t} min @ {ds_d}m (S-drill)"])
    hot = (273.15 + FILL_TEMP_C) / (273.15 + WATER_TEMP_C)
    w.writerow([f"Hot fill ({FILL_TEMP_C}°C→{WATER_TEMP_C}°C)",
                f"back {back_gas_pressure * hot:.0f} bar",
                f"EAN50 {deco_50_pressure * hot:.0f} bar",
                f"O2 {deco_o2_pressure * hot:.0f} bar"])
    return buf.getvalue().encode("utf-8-sig")


fname = f"plan_{depth}m_Tx{back_gas[0]}_{back_gas[1]}_{back_gas_pressure}bar.csv"
st.download_button(
    label="⬇️ Download CSV",
    data=_build_csv_bytes(),
    file_name=fname,
    mime="text/csv",
)
