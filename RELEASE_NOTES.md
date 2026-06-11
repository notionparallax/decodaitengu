# Release Notes

This file is required for releases.

Policy:
- Each release tag must have a matching section in this file.
- Accepted heading formats are `## vX.Y.Z` or `## X.Y.Z`.
- The publish workflow validates this before building/publishing.

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