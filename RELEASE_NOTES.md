# Release Notes

This file is required for releases.

Policy:
- Each release tag must have a matching section in this file.
- Accepted heading formats are `## vX.Y.Z` or `## X.Y.Z`.
- The publish workflow validates this before building/publishing.

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