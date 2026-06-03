# DecoDaiTengu

A modern Python dive decompression library implementing the Bühlmann ZH-L16B/C
decompression model with Erik Baker's gradient factors.

This is a modernised fork of the original [DecoTengu](http://git.savannah.gnu.org/cgit/decotengu.git)
library (v0.14.1, 2018) by Artur Wroblewski.

## Features

- **ZH-L16B-GF and ZH-L16C-GF** models with full helium compartment support (trimix)
- **Gradient factor** configuration (GF low/high)
- **CNS and OTU** oxygen toxicity tracking
- **High-level `plan_dive()` API** for common dive planning
- **Type-annotated**, Python 3.10+ codebase
- Gas mix support: air, nitrox, trimix

## Quick Start

```bash
pip install decodaitengu
```

```python
from decodaitengu import plan_dive, Gas

# Simple air dive
result = plan_dive(depth=35, bottom_time=40, gf=(30, 85))
print(f"Runtime: {result.runtime} min")
print(f"Deco stops: {[(s.depth, s.time) for s in result.stops]}")
print(f"CNS: {result.cns_percent}%")

# Trimix dive with deco gas
result = plan_dive(
    depth=60,
    bottom_time=20,
    back_gas=Gas(21, 35),
    deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
    gf=(30, 85),
)
print(f"Runtime: {result.runtime} min")
```

## Models

```python
from decodaitengu import plan_dive
from decodaitengu.models import ZHL16C, ZHL16B

# ZHL-16C is the default (recommended for dive computers)
result = plan_dive(depth=40, bottom_time=25, model=ZHL16C)

# ZHL-16B available for backward compatibility
result = plan_dive(depth=40, bottom_time=25, model=ZHL16B)
```

## Legacy API

The original DecoTengu Engine-based API has been removed. Calling
`decodaitengu.create()` raises `RuntimeError` with migration instructions.

Migration from old `decotengu`:

```python
# OLD (decotengu v0.x):
#   import decotengu
#   engine = decotengu.create()
#   engine.add_gas(0, 21)
#   profile = engine.calculate(35, 40)
#   list(profile)
#   print(engine.deco_table.total)

# NEW (decodaitengu v1.x):
from decodaitengu import plan_dive, Gas

result = plan_dive(depth=35, bottom_time=40, back_gas=Gas(21, 0), gf=(30, 85))
print(result.total_deco_time)
```

## Known Differences from Other Planners

This library uses the analytically-exact Schreiner equation for tissue loading,
whereas Subsurface (and many dive computers) use the Haldane equation with
discrete 1-second steps. The two approaches are equivalent at constant depth
but produce slightly different results during ascent/descent phases.

Key divergences from Subsurface 6.0 (ZHL-16C, GF 50/70):

| Factor | Effect | Typical magnitude |
|--------|--------|-------------------|
| Schreiner vs Haldane 1s steps | Less conservative during ascent | ±1–4 min at shallow stops |
| Gas switch timing (free ascent) | May be more conservative | +2–4 min at 3m for multi-gas |
| Helium off-gassing | Extra shallow stops for trimix | +1 stop at 18m |

Per-stop divergence is bounded at ≤5 minutes in integration tests. See
[`tests/integration/reference_data.json`](decodaitengu/tests/integration/reference_data.json)
for exact Subsurface reference values.

**This library is not a certified dive planning tool. Always validate plans
against established software and never dive beyond your training.**

## Development

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
pytest
ruff check .
```

The pre-commit hooks intentionally run check-only commands matching CI:

```bash
ruff check decodaitengu/
ruff format --check decodaitengu/
```

## License

GPL-3.0-or-later. See [COPYING](COPYING) for details.

**WARNING:** This software is provided as-is with no warranty. Any diving
using data provided by this library is at the diver's own risk.

Cheers,
gully
