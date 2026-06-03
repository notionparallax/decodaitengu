# Code Review Report: decodaitengu

Date: 2026-06-03
Reviewer: GitHub Copilot (GPT-5.3-Codex)
Scope: Whole repository with emphasis on life-critical dive-planning correctness, reliability, maintainability, readability, extensibility, usability, type safety, and documentation quality.

## Executive Summary
This codebase has a strong modernized core (typed dataclasses, clear decomposition model modules, passing tests, and lint-clean code), but it is not yet at the bar expected for life-critical dive planning software.

Primary concern: **unsafe/invalid input paths are not robustly rejected**, and there is an acknowledged algorithmic divergence from external reference software where the model can be less conservative in some profiles. Combined with stale/inaccurate public documentation and gaps in verification strategy, this creates operational and trust risk.

## Method
- Source review of core computational modules, public API, tests, packaging/CI, and docs.
- Evidence-based checks run locally:
  - `pytest`: **44 passed**
  - `ruff check`: **passed**
  - `mypy`: **failed** with strict-mode violations
- Additional runtime probes on invalid inputs to confirm behavior.

## Findings (Prioritized)

### Critical
1. Missing safety validation on core dive inputs allows physically invalid plans and runtime faults
- Why it matters: In a life-critical planner, invalid configuration must fail fast with explicit errors; silent acceptance or divide-by-zero crashes is unacceptable.
- Evidence:
  - Gas composition has no constructor validation: `Gas` can represent impossible mixes where O2 + He > 100, yielding negative N2 via computed property.
    - `decodaitengu/types.py:39`
    - `decodaitengu/types.py:57`
  - `plan_dive` normalizes GF values but does not enforce safe domain/range or monotonicity.
    - `decodaitengu/planning.py:145`
  - Rate/division points can raise runtime exceptions when rates are zero.
    - `decodaitengu/planning.py:251`
    - `decodaitengu/planning.py:303`
    - `decodaitengu/planning.py:311`
- Reproduced behavior (local probe):
  - Invalid gas `Gas(80, 30)` was accepted and produced a plan.
  - `ascent_rate=0` raised `ZeroDivisionError` instead of a controlled validation error.
  - `gf=(200, 200)` was accepted and produced a plan.
- Recommendation: Introduce explicit validation at API boundary and in data types (gas fractions, GF ranges/order, non-zero positive rates/times/depths, switch depth bounds, finite values).

2. Known model divergence includes less-conservative output in some cases without explicit safety guardrails
- Why it matters: You explicitly prioritize accuracy/reliability for life-critical use; known non-conservative differences require formal control and validation framing.
- Evidence:
  - Tests document algorithm differences from Subsurface including cases where this model is less conservative.
    - `decodaitengu/tests/test_modern.py:352`
    - `decodaitengu/tests/test_modern.py:356`
    - `decodaitengu/tests/test_modern.py:359`
- Recommendation: Add formal acceptance criteria for divergence bounds, external corpus validation against trusted references, and policy for conservative fallback where divergence direction is unfavorable.

### High
3. Public API documentation is contradictory and currently misleading
- Why it matters: Users can follow documented examples that fail at runtime, degrading trust and increasing misuse risk.
- Evidence:
  - README says legacy API is still available and shows `create()` usage:
    - `README.md:59`
    - `README.md:64`
  - Actual implementation states legacy API removed and raises runtime error:
    - `decodaitengu/__init__.py:83`
    - `decodaitengu/__init__.py:88`
  - Package docstring examples reference non-existent field `result.total_deco`:
    - `decodaitengu/__init__.py:27`
    - `decodaitengu/__init__.py:104`
- Recommendation: Align README/package docstrings with actual API (`plan_dive`, `total_deco_time`) and clearly mark legacy API status.

4. Sphinx docs are largely stale to legacy `decotengu` namespace and old architecture
- Why it matters: Documentation appears out of sync with shipped code; this is a major maintainability and usability risk.
- Evidence:
  - Legacy module references throughout docs:
    - `doc/usage.rst:4`
    - `doc/model.rst:4`
    - `doc/api.rst:16`
    - `doc/api.rst:18`
    - `doc/api.rst:40`
  - Legacy/obsolete claims (e.g., Python 3.3):
    - `doc/info.rst:37`
- Recommendation: Regenerate docs from current package (`decodaitengu`), remove dead references, and enforce docs CI build.

5. Declared strict typing posture is not currently true in CI reality
- Why it matters: For life-critical logic, type discipline is part of defect prevention.
- Evidence:
  - Strict mode configured:
    - `pyproject.toml:58`
  - Current mypy run reports errors (missing annotations):
    - `decodaitengu/planning.py:194`
    - `decodaitengu/tests/test_modern.py:370`
- Recommendation: Make mypy strict pass mandatory before release.

### Medium
6. Parameter coupling for gas tracking can fail with non-domain errors
- Why it matters: Mismatched `deco_gases` and `deco_cylinders` currently relies on `zip(..., strict=True)` behavior, which can produce generic exceptions rather than domain-specific validation.
- Evidence:
  - `decodaitengu/planning.py:166`
  - `decodaitengu/planning.py:189`
- Recommendation: Replace implicit structural failure with explicit pre-check and actionable `ValueError` message.

7. Verification strategy is mostly regression/example driven; lacks stronger safety-oriented test classes
- Why it matters: 44 passing tests are good, but insufficient for high-assurance planning software.
- Evidence:
  - Test suite currently focused in one file with limited invalid-input coverage.
    - `decodaitengu/tests/test_modern.py`
  - Only one explicit ValueError validation test identified.
    - `decodaitengu/tests/test_modern.py:286`
- Recommendation: Add property-based tests, monotonicity invariants, edge-condition fuzzing, and golden-reference datasets with pass/fail thresholds.

8. `plan_dive` is monolithic and hard to reason about in audits
- Why it matters: Large, multi-responsibility functions increase audit complexity and change risk.
- Evidence:
  - Long orchestrator function combining model loading, toxicity, gas tracking, profile capture, and stop logic.
    - `decodaitengu/planning.py:95`
- Recommendation: Decompose into validated phases (input validation, descent builder, ascent solver, tracking collectors) with unit-level contracts.

## What Is Strong
- Core equation implementation is clearly separated and documented.
  - `decodaitengu/models/base.py`
- Model parameter tables are explicit and readable.
  - `decodaitengu/models/zhl16b.py`
  - `decodaitengu/models/zhl16c.py`
- Tests and lint are currently green:
  - `pytest`: 44 passed
  - `ruff`: passed
- Data model uses dataclasses and useful typing patterns.
  - `decodaitengu/types.py`

## Framework-Oriented Assessment
Using a lightweight safety-oriented review lens (requirements traceability, defensive design, verification depth, and operational clarity):
- Requirements traceability to decompression references: **Partial**
- Defensive input handling and fail-safe behavior: **Insufficient**
- Verification breadth for safety-critical confidence: **Insufficient**
- Documentation/operational correctness: **Insufficient**
- Maintainability/modularity: **Moderate**

## Recommended Remediation Roadmap
1. Safety gate first: implement strict input validation and explicit domain errors for all public API inputs.
2. Verification uplift: add formal external validation matrix (Subsurface + known tables + edge-case corpus), with documented acceptance thresholds.
3. Documentation correction sprint: remove legacy claims, update all docs to `decodaitengu`, and enforce docs build in CI.
4. Type gate hardening: resolve mypy strict failures and require strict pass on protected branches.
5. Refactor for auditability: split `plan_dive` into smaller validated components and add invariant tests per component.

## Overall Verdict
**Not yet suitable for high-assurance, life-critical use without additional safety controls and verification hardening.**

The computational core looks promising, but correctness assurance and operational safety posture need to be materially strengthened before relying on it as a primary planning authority.
