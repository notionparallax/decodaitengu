# DecoDaiTengu - dive decompression library.
#
# Copyright (C) 2013-2014 by Artur Wroblewski <wrobell@pld-linux.org>
# Copyright (C) 2024 Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""DecoDaiTengu - dive decompression library.

A modern, typed Python library for Bühlmann ZH-L16B/C decompression
calculations with gradient factors, CNS/OTU tracking, and trimix support.

Quick start::

    from decodaitengu import plan_dive, Gas

    result = plan_dive(
        depth=35,
        bottom_time=40,
        back_gas=Gas(21, 0),  # air
        gf=(30, 85),
    )
    print(f"Runtime: {result.runtime:.0f} min")
    print(f"Deco: {result.total_deco_time:.0f} min")
    for stop in result.stops:
        print(f"  {stop.depth:.0f}m for {stop.time:.0f} min")

Trimix example::

    from decodaitengu import plan_dive, Gas, ZHL16C

    result = plan_dive(
        depth=50,
        bottom_time=25,
        back_gas=Gas(21, 35),
        deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
        model=ZHL16C,
        gf=(30, 85),
    )
"""

from .models import ZHL16B, ZHL16C, DecoModel
from .planning import plan_dive
from .tracking import CNSMethod, CNSTracker, OTUTracker
from .types import (
    Cylinder,
    DecoStop,
    DiveSummary,
    Gas,
    GasUsage,
    Phase,
    Step,
    TissueState,
)

__version__ = "1.2.0"

__all__ = [
    "plan_dive",
    "Gas",
    "ZHL16B",
    "ZHL16C",
    "DecoModel",
    "Cylinder",
    "TissueState",
    "DiveSummary",
    "DecoStop",
    "Step",
    "Phase",
    "GasUsage",
    "CNSTracker",
    "CNSMethod",
    "OTUTracker",
    # Legacy compat
    "create",
]


def create(*args: object, **kwargs: object) -> None:
    """Legacy API stub — the old Engine-based API has been removed.

    Raises RuntimeError with migration instructions.
    """
    raise RuntimeError(
        "decodaitengu.create() is no longer available.\n"
        "\n"
        "The legacy Engine API from decotengu has been replaced with a simpler\n"
        "functional API. To migrate:\n"
        "\n"
        "  OLD (decotengu):\n"
        "    import decotengu\n"
        "    engine = decotengu.create()\n"
        "    engine.add_gas(0, 21)\n"
        "    profile = engine.calculate(35, 40)\n"
        "    list(profile)\n"
        "    print(engine.deco_table.total)\n"
        "\n"
        "  NEW (decodaitengu):\n"
        "    from decodaitengu import plan_dive, Gas\n"
        "    result = plan_dive(depth=35, bottom_time=40, back_gas=Gas(21, 0))\n"
        "    print(result.total_deco_time)\n"
        "\n"
        "See README.md or https://github.com/notionparallax/decodaitengu for full docs."
    )
