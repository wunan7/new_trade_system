from trading_system.factors.registry import (
    get_all_factor_names, get_factors_by_category, FACTOR_REGISTRY, FactorCategory
)

def test_total_factor_count():
    names = get_all_factor_names()
    assert len(names) == 30, f"Expected 30 factors, got {len(names)}: {names}"

def test_technical_count():
    tech = get_factors_by_category("technical")
    assert len(tech) == 13, f"Expected 13 technical, got {len(tech)}"

def test_fundamental_count():
    fund = get_factors_by_category("fundamental")
    assert len(fund) == 13, f"Expected 13 fundamental, got {len(fund)}"

def test_money_flow_count():
    mf = get_factors_by_category("money_flow")
    assert len(mf) == 4, f"Expected 4 money_flow, got {len(mf)}"

def test_sentiment_placeholder_empty():
    assert len(get_factors_by_category("sentiment")) == 0

def test_factor_names_sorted():
    names = get_all_factor_names()
    assert names == sorted(names)

def test_nullable_valuation_factors():
    """PE/PB/PS/dividend_yield should be nullable (sparse valuation history)."""
    for name in ["pe_ttm", "pb", "ps_ttm", "dividend_yield"]:
        assert FACTOR_REGISTRY[name].nullable is True, f"{name} should be nullable"
