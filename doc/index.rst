.. rst-class:: align-center

`SOURCE CODE <https://github.com/notionparallax/decodaitengu>`_
| `ISSUES <https://github.com/notionparallax/decodaitengu/issues>`_ 

DecoDaiTengu
============

DecoDaiTengu is a Python dive decompression library implementing the
Bühlmann ZH-L16B/C decompression model with Erik Baker's gradient factors.
It is a modernised fork of the original DecoTengu library (v0.14.1, 2018).

Key features:

- ZH-L16B-GF and ZH-L16C-GF models with full helium compartment support
- Gradient factor configuration (GF low/high)
- CNS and OTU oxygen toxicity tracking
- High-level ``plan_dive()`` API for common dive planning
- Type-annotated, Python 3.10+ codebase
- Gas mix support: air, nitrox, trimix

The DecoDaiTengu library is licensed under GPL-3.0. As stated in the
license, there is no warranty — any diving using data provided by the
library is at the diver's own risk.

Table of Contents
-----------------

.. toctree::
   :maxdepth: 3

   info
   usage
   cmd
   model
   algo
   alt
   design
   api
   changelog

* :ref:`genindex`
* :ref:`search`

.. vim: sw=4:et:ai
