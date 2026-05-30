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

The original DecoTengu API is still available for backward compatibility:

```python
import decodaitengu

engine = decodaitengu.create()
engine.add_gas(0, 21)
profile = list(engine.calculate(35, 40))
print(engine.deco_table.total)  # 44.0
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

GPL-3.0-or-later. See [COPYING](COPYING) for details.

**WARNING:** This software is provided as-is with no warranty. Any diving
using data provided by this library is at the diver's own risk.

Cheers,
gully
