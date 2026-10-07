"""
Safe AST Formula Engine for KPI & Performance Calculation.
Supports Excel-like syntax, functions (IF, AND, OR, NOT, MIN, MAX, ROUND, ABS, SUM, AVG),
operators (+, -, *, /, ^, comparisons), percentage notation, and safe AST evaluation.
"""

import ast
import re
from typing import Any, Dict, List, Set


class FormulaError(Exception):
    """Custom exception for formula parsing or evaluation errors."""
    pass


class FormulaEngine:
    # Allowed math and logical functions
    FUNCTIONS = {
        "IF": lambda cond, then_val, else_val=0: then_val if cond else else_val,
        "AND": lambda *args: all(args),
        "OR": lambda *args: any(args),
        "NOT": lambda arg: not arg,
        "MIN": lambda *args: min(args) if args else 0,
        "MAX": lambda *args: max(args) if args else 0,
        "ROUND": lambda val, n=2: round(float(val), int(n)),
        "ABS": lambda val: abs(float(val)),
        "SUM": lambda *args: sum(args),
        "AVG": lambda *args: sum(args) / len(args) if args else 0,
    }

    # System variables dictionary with metadata for UI autocomplete
    CATALOG = [
        # Sales & Deals (Bitrix24 CRM)
        {"name": "deals_won_sum", "title": "Выручка (закрытые сделки)", "unit": "₽", "category": "Сделки (CRM)", "sample": 450000},
        {"name": "deals_won_count", "title": "Количество выигранных сделок", "unit": "шт", "category": "Сделки (CRM)", "sample": 12},
        {"name": "deals_total_count", "title": "Всего сделок в работе", "unit": "шт", "category": "Сделки (CRM)", "sample": 25},
        {"name": "conversion_rate", "title": "Конверсия сделок", "unit": "%", "category": "Сделки (CRM)", "sample": 48.0},
        
        # Tasks & Deadlines (Bitrix24 Tasks)
        {"name": "tasks_closed", "title": "Закрыто задач", "unit": "шт", "category": "Задачи", "sample": 28},
        {"name": "tasks_overdue", "title": "Просрочено задач", "unit": "шт", "category": "Задачи", "sample": 1},
        {"name": "tasks_total", "title": "Всего задач за период", "unit": "шт", "category": "Задачи", "sample": 30},
        {"name": "tasks_on_time_pct", "title": "% задач, закрытых вовремя", "unit": "%", "category": "Задачи", "sample": 96.4},

        # Activity & Telephony
        {"name": "calls_count", "title": "Количество звонков", "unit": "звонков", "category": "Активность", "sample": 140},
        {"name": "calls_duration_minutes", "title": "Длительность разговоров", "unit": "мин", "category": "Активность", "sample": 320},

        # Individual Targets & Salary Base
        {"name": "plan_sales", "title": "План по выручке", "unit": "₽", "category": "Планы и ставки", "sample": 400000},
        {"name": "plan_tasks", "title": "План по закрытию задач", "unit": "шт", "category": "Планы и ставки", "sample": 25},
        {"name": "target_calls", "title": "Норма звонков", "unit": "звонков", "category": "Планы и ставки", "sample": 100},
        {"name": "base_rate", "title": "Базовая ставка / Оклад", "unit": "₽", "category": "Планы и ставки", "sample": 60000},
        {"name": "bonus_limit", "title": "Максимальный лимит премии", "unit": "₽", "category": "Планы и ставки", "sample": 100000},
        {"name": "quality_score", "title": "Оценка качества работы (1-100)", "unit": "баллов", "category": "Планы и ставки", "sample": 95},
    ]

    @classmethod
    def get_catalog(cls) -> List[Dict[str, Any]]:
        return cls.CATALOG

    @classmethod
    def preprocess(cls, expr: str) -> str:
        """
        Translates Excel-style syntax into safe Python-evaluable expression:
        - Changes '^' to '**'
        - Changes '<>' to '!='
        - Changes single '=' to '==' (if not <=, >=, !=, ==)
        - Replaces uppercase Excel function names to match our dispatcher
        - Handles percentages like '15%' -> '(15 / 100)'
        """
        if not expr or not expr.strip():
            raise FormulaError("Формула не может быть пустой")

        if len(expr) > 4000:
            raise FormulaError("Длина формулы превышает максимально допустимый предел (4000 символов)")

        s = expr.strip()

        # Remove leading '=' if user pasted directly from Excel (e.g. '=IF(...)')
        if s.startswith("="):
            s = s[1:].strip()

        # Remove '@' prefix before variable names
        s = re.sub(r'@(?=[A-Za-z_])', '', s)

        # Replace power operator
        s = s.replace("^", "**")

        # Replace <> with !=
        s = s.replace("<>", "!=")

        # Replace percentages: e.g., 20% -> (20 / 100)
        s = re.sub(r'(\b\d+(?:\.\d+)?)\s*%', r'(\1 / 100)', s)

        # Replace single = with == when not part of <=, >=, !=, ==
        s = re.sub(r'(?<![<>!=])=(?!=)', '==', s)

        # Match function names case-insensitively and standardize to uppercase
        func_pattern = re.compile(r'\b(' + '|'.join(cls.FUNCTIONS.keys()) + r')\b', re.IGNORECASE)
        s = func_pattern.sub(lambda m: m.group(1).upper(), s)

        return s

    @classmethod
    def validate_ast(cls, node: ast.AST) -> None:
        """Ensure no unsafe AST nodes (no imports, no exec, no attr access)."""
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Call,
            ast.Name,
            ast.Constant,
            ast.Compare,
            ast.BoolOp,
            ast.IfExp,
            ast.Load,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
            ast.USub, ast.UAdd, ast.Not,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.And, ast.Or
        )

        for subnode in ast.walk(node):
            if not isinstance(subnode, allowed_nodes):
                raise FormulaError(f"Запрещенная конструкция в формуле: {type(subnode).__name__}")

            if isinstance(subnode, ast.Constant):
                if type(subnode.value) not in (int, float, bool):
                    raise FormulaError(f"Запрещенный тип константы: {type(subnode.value).__name__}. Разрешены только числа и логические значения.")

            if isinstance(subnode, ast.Call):
                # Ensure called object is a simple Name and is in our FUNCTIONS
                if not isinstance(subnode.func, ast.Name):
                    raise FormulaError("Вызов функций разрешен только напрямую по имени")
                func_name = subnode.func.id.upper()
                if func_name not in cls.FUNCTIONS:
                    raise FormulaError(f"Неизвестная функция: '{subnode.func.id}'. Допустимы: {', '.join(cls.FUNCTIONS.keys())}")

    @classmethod
    def extract_variables(cls, expr: str) -> Set[str]:
        """Returns the set of variable names used in the formula."""
        preprocessed = cls.preprocess(expr)
        try:
            tree = ast.parse(preprocessed, mode='eval')
        except SyntaxError as e:
            raise FormulaError(f"Ошибка синтаксиса: {e.msg} (позиция {e.offset})")

        cls.validate_ast(tree)

        variables = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
                if name.upper() not in cls.FUNCTIONS and name not in ("True", "False", "None"):
                    variables.add(name)
        return variables

    @classmethod
    def get_allowed_variable_names(cls) -> Set[str]:
        return {item["name"] for item in cls.CATALOG}

    @classmethod
    def validate(cls, expr: str) -> None:
        """
        Validates syntax, AST safety, and variable names against CATALOG.
        Raises FormulaError on any violation.
        """
        vars_used = cls.extract_variables(expr)
        allowed = cls.get_allowed_variable_names()
        unknown = sorted(list(vars_used - allowed))
        if unknown:
            allowed_str = ", ".join(sorted(allowed))
            unknown_str = ", ".join(unknown)
            raise FormulaError(f"Неизвестные переменные: {unknown_str}. Допустимые: {allowed_str}")

    @classmethod
    def evaluate(cls, expr: str, context: Dict[str, Any]) -> float:
        """
        Evaluates formula safely with given variables context.
        Returns float/int result or raises FormulaError.
        """
        preprocessed = cls.preprocess(expr)

        try:
            tree = ast.parse(preprocessed, mode='eval')
        except SyntaxError as e:
            raise FormulaError(f"Синтаксическая ошибка в формуле: {e.msg}")

        cls.validate_ast(tree)

        # Build execution environment
        env = {k: v for k, v in cls.FUNCTIONS.items()}
        # Normalize context keys to lowercase or exact
        for k, v in context.items():
            try:
                env[k] = float(v) if v is not None else 0.0
            except (ValueError, TypeError):
                env[k] = v

        try:
            compiled = compile(tree, filename="<formula>", mode="eval")
            # Evaluate with no builtins for absolute sandbox safety
            res = eval(compiled, {"__builtins__": {}}, env)
            if isinstance(res, bool):
                return 1.0 if res else 0.0
            if isinstance(res, (int, float)):
                return round(float(res), 4)
            return float(res)
        except ZeroDivisionError:
            raise FormulaError("Деление на ноль в формуле")
        except KeyError as e:
            raise FormulaError(f"Отсутствует переменная: {e}")
        except Exception as e:
            raise FormulaError(f"Ошибка вычисления формулы: {str(e)}")

    @classmethod
    def test_sandbox(cls, expr: str, custom_vars: Dict[str, Any] = None, strict: bool = True) -> Dict[str, Any]:
        """
        Sandbox endpoint helper: validates formula, extracts variables,
        checks variable names in strict mode, fills missing ones from samples,
        evaluates and returns step-by-step breakdown.
        """
        try:
            vars_used = cls.extract_variables(expr)
        except FormulaError as e:
            return {
                "valid": False,
                "error": str(e),
                "result": None,
                "variables": {},
                "used_vars": [],
                "unknown_vars": []
            }

        allowed = cls.get_allowed_variable_names()
        unknown = sorted(list(vars_used - allowed))
        if strict and unknown:
            allowed_str = ", ".join(sorted(allowed))
            unknown_str = ", ".join(unknown)
            return {
                "valid": False,
                "error": f"Неизвестные переменные: {unknown_str}. Допустимые: {allowed_str}",
                "result": None,
                "variables": {},
                "used_vars": sorted(list(vars_used)),
                "unknown_vars": unknown
            }

        # Build context from samples + custom_vars
        sample_dict = {item["name"]: item["sample"] for item in cls.CATALOG}
        context = {}
        for var in vars_used:
            if custom_vars and var in custom_vars:
                context[var] = custom_vars[var]
            elif var in sample_dict:
                context[var] = sample_dict[var]
            else:
                context[var] = 100.0  # Default fallback test value

        try:
            result = cls.evaluate(expr, context)
            return {
                "valid": True,
                "error": None,
                "result": result,
                "variables": context,
                "used_vars": sorted(list(vars_used)),
                "unknown_vars": unknown
            }
        except FormulaError as e:
            return {
                "valid": False,
                "error": str(e),
                "result": None,
                "variables": context,
                "used_vars": sorted(list(vars_used)),
                "unknown_vars": unknown
            }
