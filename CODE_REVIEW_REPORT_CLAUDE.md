# Code Review — DecoDaiTengu

- **Date:** 2026-06-03
- **Reviewer:** GitHub Copilot (Claude Opus 4.8)
- **Scope:** Whole repository, prioritising correctness/reliability for life-critical dive planning, then modernity, maintainability, readability, extensibility, usability, type safety, and documentation.
- **Independent verification run locally:**
  - `pytest` → **44 passed**
  - `ruff check decodaitengu/` → **passed**
  - `mypy decodaitengu` (config is `strict = true`) → **FAILED, 4 errors**

This review was written without reading any other review of this repository.

---

## Verdict

The computational heart of this library — the Schreiner loading equation, the Bühlmann/Baker gradient-factor ceiling, and the compartment coefficient tables — is clean, well-separated, and looks correct. The data model is modern and pleasant to read.

However, **it is not yet fit to be trusted as a primary authority for life-critical planning.** The dominant problems are (1) effectively **no input validation**, so physically impossible or degenerate inputs silently produce a "plan" or crash with a raw `ZeroDivisionError`; (2) a **silently non-functional `surface_pressure` parameter** that makes altitude planning wrong while looking supported; and (3) **documentation that ships runnable examples which throw**. The "strict typing" posture advertised in `pyproject.toml` is also not actually met.

---

## Strengths

- **Clear separation of the physics.** [decodaitengu/models/base.py](decodaitengu/models/base.py) isolates `eq_schreiner` and `eq_gf_limit` as pure functions with documented equations. This is the right shape for an auditable safety core and makes the equations independently testable.
- **Coefficient tables are explicit and spot-checkable.** [decodaitengu/models/zhl16b.py](decodaitengu/models/zhl16b.py) and [decodaitengu/models/zhl16c.py](decodaitengu/models/zhl16c.py) read straight against published Bühlmann tables (ZH-L16C compartment 1: half-life 4.0, a=1.2599, b=0.5050 — correct).
- **Modern, typed data model.** Frozen `slots` dataclasses in [decodaitengu/types.py](decodaitengu/types.py) with computed properties (`n2`, `total_pressures`) are idiomatic and immutable where it matters.
- **A `Protocol` for the model interface** ([decodaitengu/models/base.py](decodaitengu/models/base.py#L66)) is good extensibility hygiene — new models can be dropped in without touching the planner.
- **Green tests and lint.** 44 tests pass and the suite includes Schreiner values checked against known references and a `TestSubsurfaceComparison` regression class.
- **Honest documentation of model divergence** in the Subsurface comparison docstrings ([decodaitengu/tests/test_modern.py](decodaitengu/tests/test_modern.py#L357)).

---

## Findings (prioritised)

### Critical

#### C1. No input validation anywhere on the safety boundary
For life-critical software the cardinal rule is *fail fast and loud on bad input*. This code fails silently or crashes ungracefully instead.

- **Impossible gas mixes are accepted.** `Gas` has no validation, so `Gas(o2=80, he=30)` is constructed happily and its `n2` property returns **-10.0**, which then flows into alveolar pressure and tissue loading as a negative fraction.
  - [decodaitengu/types.py](decodaitengu/types.py#L38) (`Gas`), [decodaitengu/types.py](decodaitengu/types.py#L56) (`n2`)
- **Zero/negative rates crash with a raw `ZeroDivisionError`** rather than a domain error. `ascent_rate=0` divides in `current_depth / ascent_rate`.
  - [decodaitengu/planning.py](decodaitengu/planning.py#L298)
- **Gradient factors are normalised but never bounds-checked.** `gf=(200, 200)` is accepted; `gf_low > gf_high` is accepted; the heuristic `gf[0] / 100.0 if gf[0] > 1.0 else gf[0]` also silently *mis*-interprets a legitimate `gf=(1, 85)` (GF-low 1%) as GF-low 100%.
  - [decodaitengu/planning.py](decodaitengu/planning.py#L144)
- No checks that `depth`, `bottom_time`, `descent_rate`, cylinder volume/fill, or switch depths are positive and finite.

**Recommendation:** Add `__post_init__` validation to `Gas`/`Cylinder` (`0 ≤ o2`, `0 ≤ he`, `o2 + he ≤ 100`, positive volumes/fills), and a single validation block at the top of `plan_dive` raising `ValueError` with actionable messages for non-positive rates/depths/times and out-of-range/disordered GFs. This is the highest-value change in the repo.

#### C2. The `surface_pressure` parameter is largely non-functional — altitude planning is silently wrong
`plan_dive` advertises `surface_pressure` and documents it as "Surface pressure [bar]" ([decodaitengu/planning.py](decodaitengu/planning.py#L128)), but the value is **ignored by every part of the decompression calculation**:

- Tissues are initialised at the hard-coded module constant, not the parameter: `tissues = deco_model.init(const.SURFACE_PRESSURE)` — [decodaitengu/planning.py](decodaitengu/planning.py#L162).
- Depth↔pressure conversion uses the constant, not the parameter — [decodaitengu/planning.py](decodaitengu/planning.py#L55) and [decodaitengu/planning.py](decodaitengu/planning.py#L60).
- Surfacing/ceiling comparisons test against `const.SURFACE_PRESSURE` — [decodaitengu/planning.py](decodaitengu/planning.py#L309), [decodaitengu/planning.py](decodaitengu/planning.py#L414).
- The parameter is used in *only one place*: scaling gas-consumption litres — [decodaitengu/planning.py](decodaitengu/planning.py#L172).

So a user planning an altitude dive (e.g. `surface_pressure=0.79`) gets a sea-level decompression schedule with a false sense of correctness, plus internally inconsistent gas-consumption numbers. A silently-ignored safety parameter is worse than an absent one.

**Recommendation:** Either thread `surface_pressure` through `init`, the depth/pressure conversions, and the surfacing checks, or remove the parameter entirely and document that only sea-level planning is supported. Do not ship it half-wired.

---

### High

#### H1. Shipped documentation examples raise at runtime
- **`result.total_deco` does not exist** — the field is `total_deco_time` ([decodaitengu/types.py](decodaitengu/types.py#L205)). The package docstring quick-start and the migration example both print `result.total_deco`, which raises `AttributeError`.
  - [decodaitengu/__init__.py](decodaitengu/__init__.py#L27), [decodaitengu/__init__.py](decodaitengu/__init__.py#L104)
- **The README "Legacy API" section is fiction.** It shows `decodaitengu.create()` returning a working engine and `deco_table.total  # 44.0`, but `create()` unconditionally raises `RuntimeError`.
  - [README.md](README.md#L57) vs [decodaitengu/__init__.py](decodaitengu/__init__.py#L80)

**Recommendation:** Fix the docstring field name and rewrite the README legacy section to state the API was removed (the `create()` stub message itself is good — mirror it). Add a doctest/CI smoke test so example drift fails the build.

#### H2. "Strict typing" is advertised but not enforced
`pyproject.toml` sets `strict = true` ([pyproject.toml](pyproject.toml#L57)), yet `mypy` fails:
```
decodaitengu/planning.py:194: error: Function is missing a type annotation for one or more parameters
decodaitengu/tests/test_modern.py:370: missing return type / missing param annotation / Missing type arguments for "dict"
```
The offending nested helper is `_snapshot_state(..., snap_tissues, snap_gf)` — [decodaitengu/planning.py](decodaitengu/planning.py#L194). For safety-critical code, the type gate should be a hard release blocker, not aspirational.

**Recommendation:** Annotate `snap_tissues: TissueState` and `snap_gf: float`, fix the test helper, and make `mypy` mandatory in CI / pre-commit.

#### H3. CNS exponential model rests on an unverifiable, suspiciously-dated source
The default CNS method uses a curve-fit attributed to a forum post by "pig, 2026" ([decodaitengu/tracking/cns.py](decodaitengu/tracking/cns.py#L94)). The magic constants (`30.05712`, `1.35667`, the `exp`/`exp` blend) are opaque and the cited future date (2026) undermines confidence in provenance for a toxicity figure divers may rely on.

**Recommendation:** Make the auditable `NOAA_TABLE` method the default (it traces directly to published limits), keep the exponential as opt-in, and add a test asserting the exponential curve stays within tolerance of the NOAA table across PO2 0.5–1.6 so the fit cannot silently drift.

---

### Medium

#### M1. `plan_dive` is a ~360-line monolith — hard to audit and to test in units
[decodaitengu/planning.py](decodaitengu/planning.py#L95) interleaves model construction, GF normalisation, descent (with optional stops), bottom loop, NDL check, ascent/stop solver, and four parallel tracking concerns (CNS, OTU, gas, profile snapshots) in one scope with many `_`-prefixed locals and closures. This raises change-risk and defeats per-phase verification.

**Recommendation:** Extract `_validate_inputs`, `_resolve_model`, `_descend`, `_bottom`, `_ascend_with_deco`, each returning explicit state, and unit-test each against invariants.

#### M2. Deco gas selection during ascent may not pick the optimal mix
The switch logic iterates `all_gases` (sorted *deepest switch first*) and takes the first gas with `switch_depth >= stop_depth` ([decodaitengu/planning.py](decodaitengu/planning.py#L390)). With conventional mixes the deepest-eligible gas is the *leanest* eligible one, so this can select a less-oxygen-rich gas than the diver intends at a given stop, lengthening deco or diverging from operator expectation. It works for typical configs but is fragile.

**Recommendation:** At each stop choose the breathable gas with the highest O2 whose `switch_depth >= stop_depth` (subject to a PO2 ceiling), and add a test with overlapping switch depths.

#### M3. `NDL` is declared but never computed
`DiveSummary.ndl` exists ([decodaitengu/types.py](decodaitengu/types.py#L208)) but every return path sets `ndl=None`, including the no-decompression branch ([decodaitengu/planning.py](decodaitengu/planning.py#L334)). Users cannot obtain a no-deco limit — a core planning number — so the field is misleading.

**Recommendation:** Either compute and populate NDL on the no-deco path or remove the field until implemented.

#### M4. Cylinder/gas pairing fails with a generic structural error
Mismatched `deco_gases`/`deco_cylinders` length surfaces only via `zip(..., strict=True)` ([decodaitengu/planning.py](decodaitengu/planning.py#L188)), giving a generic `ValueError` rather than a clear "N deco gases but M deco cylinders" message.

**Recommendation:** Pre-check lengths and raise an explicit, named error.

#### M5. Verification breadth is thin for a safety library
All new-code tests live in a single file and lean on regression/example assertions; only one invalid-input case exists (`test_bottom_time_validation`). `hypothesis` is a declared dev dependency but unused.

**Recommendation:** Add property-based tests for the invariants that *must* hold (more conservative GF ⇒ ≥ deco; deeper/longer ⇒ ≥ loading; monotonic tissue loading at constant depth; ceiling never below surface after a valid surfacing), plus a golden-reference corpus with documented tolerance bands.

---

### Low / polish

- **Dead `alt/` package.** `decodaitengu/alt/` (and `tests/alt/`) contain no source — only stale `__pycache__`. Remove to reduce audit surface.
- **Function-local `import math`** inside `_exponential_cns_rate` ([decodaitengu/tracking/cns.py](decodaitengu/tracking/cns.py#L113)) — hoist to module top for consistency with the rest of the codebase.
- **Sphinx docs under `doc/` still reference the legacy `decotengu` namespace and architecture** (e.g. [doc/usage.rst](doc/usage.rst), [doc/api.rst](doc/api.rst)). They should be regenerated against `decodaitengu` and built in CI, or removed until rewritten.
- **`Step.depth` hard-codes `1.01325` / `0.09985`** ([decodaitengu/types.py](decodaitengu/types.py#L139)) instead of using `const`. Minor duplication risk if constants ever change.

---

## Assessment against a safety-review lens

| Dimension | Rating | Note |
|---|---|---|
| Defensive input handling / fail-safe | **Insufficient** | No validation; raw crashes; silently-ignored safety parameter (C1, C2) |
| Correctness of core equations | **Good** | Schreiner/Baker and coefficient tables check out |
| Verification depth | **Insufficient** | Single test file, one invalid-input test, `hypothesis` unused |
| Type discipline (as configured) | **Not met** | `strict=true` but mypy fails |
| Documentation accuracy | **Insufficient** | Runnable examples raise; legacy docs stale |
| Maintainability / modularity | **Moderate** | Strong model layer; monolithic planner |
| Extensibility | **Good** | `Protocol`-based model interface |

---

## Recommended remediation order

1. **C1 + C2** — add input validation and either wire or remove `surface_pressure`. (Safety gate.)
2. **H2** — make `mypy --strict` pass and enforce it in CI.
3. **H1** — fix the docstring/README examples and add an example smoke test.
4. **H3** — default to the auditable NOAA CNS method; bound the exponential fit with a test.
5. **M5** — add property-based invariants and a golden-reference corpus with tolerances.
6. **M1–M4, Low items** — decompose `plan_dive`, fix gas selection, resolve `NDL`, clarify pairing errors, delete dead code, refresh docs.

**Bottom line:** a promising, well-structured core wrapped in an under-defended, under-verified, and partly-misdocumented shell. Close the validation and documentation gaps and enforce the type gate before anyone treats its output as authoritative.
