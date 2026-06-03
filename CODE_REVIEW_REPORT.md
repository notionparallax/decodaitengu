# Code Review Report: decodaitengu (Updated)

Date: 2026-06-03
Reviewer: GitHub Copilot (GPT-5.3-Codex)
Scope: Full repository, with priority on life-critical dive-planning accuracy and reliability, then maintainability, readability, extensibility, usability, doc quality, and typing.

## Findings (Prioritized)

### High
1. No oxygen partial-pressure safety envelope validation for configured gas switch depths
- Why this matters: The planner now validates many inputs, but it can still accept physiologically unsafe gas-switch plans without warning.
- Evidence:
  - Validation checks switch-depth sign/range only, not PO2 safety at switch depth:
    - `decodaitengu/planning.py:185`
    - `decodaitengu/planning.py:187`
  - Runtime probe accepted a plan with 100% O2 switch at 30 m (very high PO2) and returned a schedule successfully.
- Risk: Unsafe user configuration may look valid and produce misleadingly authoritative output.
- Recommendation: Add explicit configurable PO2 limits (for travel/deco) and reject switch points exceeding limit; include tests for over-limit rejection.

### Medium
2. Cylinder mismatch error message is clear but contains duplicated wording
- Evidence:
  - Duplicated segment in error text construction:
    - `decodaitengu/planning.py:620`
- Impact: Readability/UX issue when diagnosing input mistakes.
- Recommendation: Fix the duplicate fragment in the exception string.

3. Internal docstring drift: mentions a non-existent exception path
- Evidence:
  - `_validate_inputs` docstring claims `NotImplementedError` for altitude diving, but altitude is now implemented and validated:
    - `decodaitengu/planning.py:155`
- Impact: Minor maintenance confusion.
- Recommendation: Remove/update that docstring line.

4. Packaging metadata lags CI support matrix
- Evidence:
  - CI tests Python 3.14:
    - `.github/workflows/ci.yml:14`
  - Project classifiers list through 3.13 only:
    - `pyproject.toml:22`
- Impact: Minor ecosystem signaling mismatch.
- Recommendation: Add Python 3.14 classifier if officially supported.

## Major Improvements Since Last Review

1. Input validation hardening is substantial
- Gas and cylinder validation added in data types:
  - `decodaitengu/types.py:57`
  - `decodaitengu/types.py:96`
- Planner parameter validation now covers depth/time/rates/GF/surface pressure/deco switch bounds:
  - `decodaitengu/planning.py:140`

2. Planner architecture is significantly more maintainable
- `plan_dive` decomposed into focused helpers (`_validate_inputs`, `_resolve_model`, `_descend`, `_bottom`, `_ascend_with_deco`) and structured state object:
  - `decodaitengu/planning.py:140`
  - `decodaitengu/planning.py:219`
  - `decodaitengu/planning.py:303`
  - `decodaitengu/planning.py:331`
  - `decodaitengu/planning.py:527`

3. Altitude handling now appears implemented end-to-end
- Surface pressure is threaded through depth/pressure conversions and model init:
  - `decodaitengu/planning.py:52`
  - `decodaitengu/planning.py:57`
  - `decodaitengu/planning.py:598`

4. Test suite coverage and rigor improved dramatically
- Validation-focused tests:
  - `decodaitengu/tests/test_validation.py`
- Property-based invariants:
  - `decodaitengu/tests/test_properties.py`
- Documentation smoke tests:
  - `decodaitengu/tests/test_doc_examples.py`
- Divergence/regression integration checks:
  - `decodaitengu/tests/integration/test_divergence.py`

5. Documentation/API consistency improved
- README and package docstring now align with `total_deco_time` and legacy-API removal.
  - `README.md:57`
  - `decodaitengu/__init__.py:27`

## Verification Results (Current State)
- `pytest -q`: 168 passed
- `ruff check decodaitengu`: passed
- `mypy --strict decodaitengu`: success (no issues in 20 source files)

## Overall Verdict
The repository has moved from "not yet suitable" to **promising and materially improved**, with strong progress on safety validation, typing, modularity, and verification discipline.

For life-critical trust, the main remaining technical gap is explicit PO2 safety-envelope validation for gas-switch configuration. Addressing that, plus the minor documentation/metadata polish items above, would put the project in notably better operational shape.
