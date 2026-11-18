"""pricing.yaml: standard and flex prices."""

import pytest

from bench.run import load_pricing


@pytest.fixture
def pricing(tmp_path):
    path = tmp_path / "pricing.yaml"
    path.write_text(
        "- id: openai/a\n  price: [2.0, 10.0]\n  flex: 0.5\n"
        "- id: anthropic/b\n  price: [1.0, 5.0]\n"
        "- id: openai/c\n  price: [1.0, 1.0]\n  flex: 2\n",
        encoding="utf-8",
    )
    return load_pricing(path)


def test_flex_price(pricing):
    assert pricing.price("openai/a", "openrouter") == (2.0, 10.0)
    assert pricing.price("openai/a", "openrouter", flex=True) == (1.0, 5.0)


def test_no_flex_ratio_keeps_standard_price(pricing):
    assert pricing.price("anthropic/b", "openrouter", flex=True) == (1.0, 5.0)
    assert not pricing.flex_available("anthropic/b", "openrouter")


def test_flex_only_through_openrouter(pricing):
    assert pricing.flex_available("openai/a", "openrouter")
    assert not pricing.flex_available("openai/a", "openai")


def test_invalid_ratio_is_an_error(pricing):
    assert any("flex must be a ratio" in i.message for i in pricing.issues)
    assert pricing.flex_ratio("openai/c", "openrouter") is None
