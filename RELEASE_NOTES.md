# Release Notes

This file is required for releases.

Policy:
- Each release tag must have a matching section in this file.
- Accepted heading formats are `## vX.Y.Z` or `## X.Y.Z`.
- The publish workflow validates this before building/publishing.

## v1.4.1

- Fix: ascent gas-switch pause now fires when `current_depth` (where we are)
  is a switch depth, not `target_depth` (where we're going). Previously the
  pause was skipped in the most common single-deco-gas case.
- Fix: descent gas-switch pause now loads tissues with the NEW gas (the gas the
  diver has just switched to), not the old gas.
- Fix: gas-switch pauses now also fire at deco stop depths, not only during
  free ascent. This means switches from back gas to EAN50 at the first stop
  depth are correctly counted with the configured switch time.
- Tests: added `TestGasSwitchTime` suite verifying switch-time behaviour.

## v1.4.0

- Unified gas list API: `plan_dive(gases=[...], cylinders=[...])` replaces
  separate `back_gas` + `deco_gases` for multi-gas planning.
- `Gas`: new `use_on_descent: bool = False` and `use_on_ascent: bool = True`
  fields. Back/travel gases set `use_on_descent=True`; travel-only gases
  additionally set `use_on_ascent=False`.
- Descent now selects the richest eligible descent gas at each depth, with
  automatic gas-switch breakpoints at each `switch_depth` boundary. Travel
  gas (e.g. air surface to 40 m on a hypoxic H2 dive) is handled natively
  without app-layer workarounds.
- Legacy `back_gas` / `deco_gases` / `back_cylinder` / `deco_cylinders` API
  remains fully backward compatible via an internal shim.
- `plan_dive()`: new `gas_switch_time: float = 1.0` parameter — diver pauses this many
  minutes at each gas switch depth (applies to both descent and ascent switches).
  Set to 0.0 for on-the-fly switching with no stop.

## v1.3.1

- Fix #45: switch to richest eligible gas during free ascent from bottom
  to first stop, and during NDL ascent. Gas switch depths are now treated
  as breakpoints alongside ascent-rate breakpoints, matching Subsurface
  behaviour.

## v1.3.0

- Add experimental H2 (hydrogen) gas support (Hydreliox mixes).
- Gas: new `h2` field; O2 ≤ 4% enforced when H2 > 0 (flammability limit).
- TissueState: `h2_pressures` compartment loading via Schreiner equation.
- DiveSummary: `max_pph2` tracking.
- ZHL-16C/B: H2 half-times derived from He via diffusion-theory scaling
  (factor ≈ 0.71). **EXPERIMENTAL — no validated coefficients exist.**
- planning.py: H2 gas density, max_pph2 tracking, UserWarning when H2 present.

## v1.2.1

- Fix NDL ascent path to step through ascent-rate breakpoints, recording
  a snapshot at each step so the depth profile and ceiling band render
  correctly when a segmented ascent rate is configured.
- Fix deco free ascent (depth to first stop) to likewise step through
  rate-change breakpoints, preventing the slope from appearing blended
  across segments (most visible on the Bounce scenario).

## v1.2.0

- Added segmented ascent support to plan_dive.
- ascent_rate now accepts:
  - float (single ascent rate)
  - list of (max_depth_m, rate_m_per_min)
  - dict mapping max_depth_m to rate_m_per_min
- Added validation and behavior tests for segmented ascent profiles.
- Updated README with segmented ascent examples and usage rules.