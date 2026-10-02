"""Tiny, safe ``{{ }}`` templating and a restricted ``when`` expression evaluator.

No ``eval``/``exec`` anywhere. The templating engine resolves a dotted path
(``ws``, ``period``, ``steps.<id>.status``, ``steps.<id>.body.<key>``...) against a
plain dict context. The expression evaluator supports a tiny grammar sufficient for
``when:`` clauses: comparisons (``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``), boolean
``and``/``or``/``not``, ``len(x)``, integer/float/string literals, and dotted paths.
"""

from __future__ import annotations

import re
from typing import Any

_PATH = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")

#: Longest dotted path a template may walk.
MAX_TEMPLATE_DEPTH = 16


def resolve_path(path: str, context: dict[str, Any]) -> Any:
    """Walk ``a.b.0.c`` through plain dicts (key lookup) and lists (integer index) ONLY. No
    ``getattr`` — ``{{ steps.x.body.__class__ }}`` is a ``KeyError``, as is any part starting with
    ``_`` and any path deeper than ``MAX_TEMPLATE_DEPTH``."""
    parts = path.split(".")
    if len(parts) > MAX_TEMPLATE_DEPTH:
        raise KeyError(f"template path too deep: {path!r} (max {MAX_TEMPLATE_DEPTH})")
    node: Any = context
    for part in parts:
        if part.startswith("_"):
            raise KeyError(f"template path part not allowed: {part!r}")
        if isinstance(node, dict):
            if part not in node:
                raise KeyError(f"unknown template path: {path!r} (missing {part!r})")
            node = node[part]
        elif isinstance(node, list | tuple):
            if not part.isdigit() or int(part) >= len(node):
                raise KeyError(f"unknown template path: {path!r} (bad index {part!r})")
            node = node[int(part)]
        else:
            raise KeyError(f"unknown template path: {path!r} (cannot descend into {type(node).__name__} at {part!r})")
    return node


def render_value(value: Any, context: dict[str, Any]) -> Any:
    """Render ``{{ }}`` placeholders. A string that is *exactly* one placeholder keeps
    the resolved value's type (e.g. an int); anything else is stringified."""
    if isinstance(value, str):
        m = _PATH.fullmatch(value.strip())
        if m:
            return resolve_path(m.group(1), context)

        def _sub(match: re.Match) -> str:
            return str(resolve_path(match.group(1), context))

        return _PATH.sub(_sub, value)
    if isinstance(value, dict):
        return {k: render_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [render_value(v, context) for v in value]
    return value


# --------------------------------------------------------------------------- when

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<num>\d+\.\d+|\d+)
    |   (?P<str>'[^']*'|"[^"]*")
    |   (?P<op>==|!=|<=|>=|<|>)
    |   (?P<lparen>\()
    |   (?P<rparen>\))
    |   (?P<comma>,)
    |   (?P<kw>and|or|not|len|True|False|None)
    |   (?P<id>[a-zA-Z_][a-zA-Z0-9_.]*)
    )""",
    re.VERBOSE,
)


class ExprError(ValueError):
    pass


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise ExprError(f"unexpected character at {pos!r} in when-expression: {expr!r}")
        kind = m.lastgroup
        tokens.append((kind, m.group(kind)))
        pos = m.end()
    return tokens


class _Parser:
    """Recursive-descent parser/evaluator for a tiny boolean-expression grammar.

    Grammar (loosest to tightest binding):
        expr    := or_expr
        or_expr := and_expr ("or" and_expr)*
        and_expr:= not_expr ("and" not_expr)*
        not_expr:= "not" not_expr | comparison
        comparison := atom (( "==" | "!=" | "<" | "<=" | ">" | ">=" ) atom)?
        atom    := NUMBER | STRING | "True" | "False" | "None"
                 | "len" "(" expr ")" | IDENT | "(" expr ")"
    """

    def __init__(self, tokens: list[tuple[str, str]], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.i = 0
        self.context = context

    def _peek(self) -> tuple[str, str] | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def _advance(self) -> tuple[str, str]:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self) -> Any:
        result = self._or_expr()
        if self._peek() is not None:
            raise ExprError(f"unexpected trailing token: {self._peek()}")
        return result

    def _or_expr(self) -> Any:
        value = self._and_expr()
        while self._peek() == ("kw", "or"):
            self._advance()
            value = bool(value) or bool(self._and_expr())
        return value

    def _and_expr(self) -> Any:
        value = self._not_expr()
        while self._peek() == ("kw", "and"):
            self._advance()
            value = bool(value) and bool(self._not_expr())
        return value

    def _not_expr(self) -> Any:
        if self._peek() == ("kw", "not"):
            self._advance()
            return not bool(self._not_expr())
        return self._comparison()

    def _comparison(self) -> Any:
        left = self._atom()
        peek = self._peek()
        if peek and peek[0] == "op":
            op = self._advance()[1]
            right = self._atom()
            ops = {
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                "<": lambda a, b: a < b,
                "<=": lambda a, b: a <= b,
                ">": lambda a, b: a > b,
                ">=": lambda a, b: a >= b,
            }
            return ops[op](left, right)
        return left

    def _atom(self) -> Any:
        tok = self._peek()
        if tok is None:
            raise ExprError("unexpected end of when-expression")
        kind, text = tok
        if kind == "num":
            self._advance()
            return float(text) if "." in text else int(text)
        if kind == "str":
            self._advance()
            return text[1:-1]
        if kind == "kw" and text == "True":
            self._advance()
            return True
        if kind == "kw" and text == "False":
            self._advance()
            return False
        if kind == "kw" and text == "None":
            self._advance()
            return None
        if kind == "kw" and text == "len":
            self._advance()
            if self._advance() != ("lparen", "("):
                raise ExprError("expected '(' after len")
            value = self._or_expr()
            if self._advance() != ("rparen", ")"):
                raise ExprError("expected ')' to close len(...)")
            return len(value)
        if kind == "lparen":
            self._advance()
            value = self._or_expr()
            if self._advance() != ("rparen", ")"):
                raise ExprError("expected ')' ")
            return value
        if kind == "id":
            self._advance()
            return resolve_path(text, self.context)
        raise ExprError(f"unexpected token: {tok}")


def eval_when(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a restricted boolean expression. Never uses ``eval``/``exec``."""
    tokens = _tokenize(expr)
    try:
        result = _Parser(tokens, context).parse()
    except (KeyError, AttributeError, IndexError) as e:
        raise ExprError(f"error evaluating when-expression {expr!r}: {e}") from e
    return bool(result)
