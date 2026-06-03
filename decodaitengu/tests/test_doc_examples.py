#
# DecoTengu - dive decompression library.
#
# Smoke tests for documented examples (Issue #4: H1).
# Ensures that examples in README and package docstrings actually work.
#

from decodaitengu import ZHL16C, Gas, plan_dive


class TestDocumentedExamples:
    """Verify all examples from README and package docstrings run without error."""

    def test_readme_simple_air_dive(self):
        """README Quick Start: simple air dive."""
        result = plan_dive(depth=35, bottom_time=40, gf=(30, 85))
        assert result.runtime > 0
        assert isinstance(result.stops, list)
        assert result.cns_percent >= 0

    def test_readme_trimix_with_deco(self):
        """README Quick Start: trimix dive with deco gas."""
        result = plan_dive(
            depth=60,
            bottom_time=20,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
            gf=(30, 85),
        )
        assert result.runtime > 0

    def test_readme_model_selection(self):
        """README Models section: model selection."""
        from decodaitengu.models import ZHL16B, ZHL16C

        result_c = plan_dive(depth=40, bottom_time=25, model=ZHL16C, gf=(30, 85))
        result_b = plan_dive(depth=40, bottom_time=25, model=ZHL16B, gf=(30, 85))
        assert result_c.runtime > 0
        assert result_b.runtime > 0

    def test_init_docstring_quick_start(self):
        """Package docstring quick start example."""
        result = plan_dive(
            depth=35,
            bottom_time=40,
            back_gas=Gas(21, 0),
            gf=(30, 85),
        )
        # Verify the fields referenced in the docstring exist and are sensible
        assert hasattr(result, "runtime")
        assert hasattr(result, "total_deco_time")
        assert hasattr(result, "stops")
        _ = f"Runtime: {result.runtime:.0f} min"
        _ = f"Deco: {result.total_deco_time:.0f} min"

    def test_init_docstring_trimix_example(self):
        """Package docstring trimix example."""
        result = plan_dive(
            depth=50,
            bottom_time=25,
            back_gas=Gas(21, 35),
            deco_gases=[Gas(50, 0, switch_depth=21), Gas(100, 0, switch_depth=6)],
            model=ZHL16C,
            gf=(30, 85),
        )
        assert result.runtime > 0

    def test_create_raises_runtime_error(self):
        """Legacy create() should raise RuntimeError with migration info."""
        import pytest

        from decodaitengu import create

        with pytest.raises(RuntimeError, match="no longer available"):
            create()
