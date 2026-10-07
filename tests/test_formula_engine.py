import pytest
import sys
import os

# Add parent directory to sys.path so app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.formula_engine import FormulaEngine, FormulaError


def test_basic_arithmetic():
    assert FormulaEngine.evaluate("10 + 20 * 3", {}) == 70.0
    assert FormulaEngine.evaluate("(10 + 20) * 3", {}) == 90.0
    assert FormulaEngine.evaluate("2 ^ 3", {}) == 8.0
    assert FormulaEngine.evaluate("100 * 15%", {}) == 15.0


def test_functions():
    assert FormulaEngine.evaluate("MIN(10, 20, 5, 40)", {}) == 5.0
    assert FormulaEngine.evaluate("MAX(10, 20, 5, 40)", {}) == 40.0
    assert FormulaEngine.evaluate("ROUND(123.4567, 2)", {}) == 123.46
    assert FormulaEngine.evaluate("ABS(-55.5)", {}) == 55.5
    assert FormulaEngine.evaluate("SUM(10, 20, 30)", {}) == 60.0
    assert FormulaEngine.evaluate("AVG(10, 20, 30)", {}) == 20.0


def test_if_and_or_logic():
    # Simple IF
    assert FormulaEngine.evaluate("IF(10 > 5, 100, 50)", {}) == 100.0
    assert FormulaEngine.evaluate("IF(10 < 5, 100, 50)", {}) == 50.0

    # Complex KPI logic with AND / OR
    expr = "IF(AND(sales >= plan, tasks_overdue == 0), base * 1.5, base * (sales / plan))"
    ctx1 = {"sales": 500000, "plan": 400000, "tasks_overdue": 0, "base": 60000}
    assert FormulaEngine.evaluate(expr, ctx1) == 90000.0  # 60000 * 1.5

    ctx2 = {"sales": 300000, "plan": 400000, "tasks_overdue": 0, "base": 60000}
    assert FormulaEngine.evaluate(expr, ctx2) == 45000.0  # 60000 * (3/4)


def test_excel_syntax_compatibility():
    # Excel single '=' comparison and case-insensitivity
    assert FormulaEngine.evaluate("=if(sales = 100, 500, 0)", {"sales": 100}) == 500.0
    assert FormulaEngine.evaluate("=IF(sales <> 100, 500, 0)", {"sales": 200}) == 500.0


def test_sandbox_testing():
    res = FormulaEngine.test_sandbox("IF(deals_won_sum >= plan_sales, base_rate * 1.2, base_rate)")
    assert res["valid"] is True
    assert res["result"] is not None
    assert "deals_won_sum" in res["used_vars"]
    assert "plan_sales" in res["used_vars"]
    assert "base_rate" in res["used_vars"]


def test_security_blocking():
    # Disallow imports, exec, attributes
    with pytest.raises(FormulaError):
        FormulaEngine.evaluate("__import__('os').system('dir')", {})

    with pytest.raises(FormulaError):
        FormulaEngine.evaluate("eval('1+1')", {})

    with pytest.raises(FormulaError):
        FormulaEngine.evaluate("open('secret.txt').read()", {})


def test_zero_division_raises_formula_error():
    with pytest.raises(FormulaError, match="Деление на ноль"):
        FormulaEngine.evaluate("1 / 0", {})


def test_string_and_bytes_constants_forbidden():
    with pytest.raises(FormulaError, match="Запрещенный тип константы"):
        FormulaEngine.evaluate("'abc' * 10", {})

    with pytest.raises(FormulaError, match="Запрещенный тип константы"):
        FormulaEngine.evaluate("100 + 'hello'", {})


def test_formula_length_limit():
    long_expr = "1 + " * 1500 + "1"  # > 4000 chars
    assert len(long_expr) > 4000
    with pytest.raises(FormulaError, match="Длина формулы превышает"):
        FormulaEngine.evaluate(long_expr, {})


def test_at_prefix_variable_evaluation():
    ctx = {"base_rate": 50000, "deals_won_sum": 300000}
    res_at = FormulaEngine.evaluate("@base_rate + @deals_won_sum * 0.1", ctx)
    res_no_at = FormulaEngine.evaluate("base_rate + deals_won_sum * 0.1", ctx)
    assert res_at == res_no_at == 80000.0


def test_boolean_result_evaluation():
    assert FormulaEngine.evaluate("10 > 5", {}) == 1.0
    assert FormulaEngine.evaluate("10 < 5", {}) == 0.0

