"""Advanced condition parser supporting AND/OR/NOT, regex, temporal, and nested conditions.

Parses a string expression into a Condition or CompoundCondition tree.
Supports:
  - Simple: ``field op value``  (e.g. ``risk_score >= 0.9``)
  - Compound: ``expr AND expr``, ``expr OR expr``, ``NOT expr``
  - Parentheses: ``(expr AND expr) OR expr``
  - Regex: ``field =~ 'pattern'``
  - Temporal: ``field after '2025-01-01'``, ``field before '2025-12-31'``
  - Membership: ``field in [a, b, c]``, ``field not_in [a, b, c]``
  - String ops: ``field contains 'x'``, ``field starts_with 'x'``, ``field ends_with 'x'``
  - Existence: ``field exists``
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from q_guardian.policy.data import CompoundCondition, Condition
from q_guardian.policy.enums import (
    ComparisonOperator,
    ConditionType,
    LogicalOperator,
)
from q_guardian.policy.exceptions import ConditionParseError


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_SPEC = [
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("LBRACKET", r"\["),
    ("RBRACKET", r"\]"),
    ("AND", r"\bAND\b"),
    ("OR", r"\bOR\b"),
    ("NOT", r"\bNOT\b"),
    ("EXISTS", r"\bexists\b"),
    ("AFTER", r"\bafter\b"),
    ("BEFORE", r"\bbefore\b"),
    ("IN", r"\bin\b(?=\s*\[)"),
    ("NOT_IN", r"\bnot_in\b(?=\s*\[)"),
    ("MATCHES", r"=~"),
    ("NOT_MATCHES", r"!~"),
    ("GTE", r">="),
    ("LTE", r"<="),
    ("NEQ", r"!="),
    ("EQ", r"=="),
    ("GT", r">"),
    ("LT", r"<"),
    ("CONTAINS", r"\bcontains\b"),
    ("STARTS_WITH", r"\bstarts_with\b"),
    ("ENDS_WITH", r"\bends_with\b"),
    ("COMMA", r","),
    ("STRING", r"'[^']*'|\"[^\"]*\""),
    ("NUMBER", r"-?\d+(?:\.\d+)?"),
    ("IDENT", r"[A-Za-z_][A-Za-z0-9_]*"),
    ("SKIP", r"\s+"),
]

_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC)
)


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, type_: str, value: str) -> None:
        self.type = type_
        self.value = value

    def __repr__(self) -> str:
        return f"Token({self.type}, {self.value!r})"


def _tokenize(expr: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    for m in _TOKEN_RE.finditer(expr):
        # Check for gaps (unrecognized characters)
        if m.start() > pos:
            gap = expr[pos : m.start()]
            raise ConditionParseError(
                f"Unexpected character(s) at position {pos}: {gap!r}"
            )
        kind = m.lastgroup or ""
        value = m.group()
        if kind == "SKIP":
            pos = m.end()
            continue
        if kind is None:
            raise ConditionParseError(
                f"Unexpected character at position {m.start()}: {value!r}"
            )
        tokens.append(_Token(kind, value))
        pos = m.end()
    # Check for trailing unrecognized characters
    if pos < len(expr):
        trailing = expr[pos:]
        raise ConditionParseError(
            f"Unexpected trailing character(s): {trailing!r}"
        )
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

class _Parser:
    """Recursive-descent parser for the condition DSL."""

    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, type_: str) -> _Token:
        tok = self._peek()
        if tok is None or tok.type != type_:
            actual = tok.type if tok else "EOF"
            raise ConditionParseError(f"Expected {type_}, got {actual}")
        return self._advance()

    def parse(self) -> Condition | CompoundCondition:
        result = self._parse_or()
        if self._pos < len(self._tokens):
            raise ConditionParseError(
                f"Unexpected token after expression: {self._tokens[self._pos]!r}"
            )
        return result

    def _parse_or(self) -> Condition | CompoundCondition:
        left = self._parse_and()
        while self._peek() and self._peek().type == "OR":
            self._advance()
            right = self._parse_and()
            if isinstance(left, CompoundCondition) and left.operator == LogicalOperator.OR:
                left.conditions.append(right)
            else:
                left = CompoundCondition(
                    operator=LogicalOperator.OR, conditions=[left, right]
                )
        return left

    def _parse_and(self) -> Condition | CompoundCondition:
        left = self._parse_not()
        while self._peek() and self._peek().type == "AND":
            self._advance()
            right = self._parse_not()
            if isinstance(left, CompoundCondition) and left.operator == LogicalOperator.AND:
                left.conditions.append(right)
            else:
                left = CompoundCondition(
                    operator=LogicalOperator.AND, conditions=[left, right]
                )
        return left

    def _parse_not(self) -> Condition | CompoundCondition:
        if self._peek() and self._peek().type == "NOT":
            self._advance()
            inner = self._parse_primary()
            return CompoundCondition(
                operator=LogicalOperator.NOT, conditions=[inner]
            )
        return self._parse_primary()

    def _parse_primary(self) -> Condition | CompoundCondition:
        tok = self._peek()
        if tok is None:
            raise ConditionParseError("Unexpected end of expression")

        # Parenthesized expression
        if tok.type == "LPAREN":
            self._advance()
            expr = self._parse_or()
            self._expect("RPAREN")
            return expr

        # Temporal: field after/before 'date'
        if tok.type == "IDENT" and self._pos + 1 < len(self._tokens):
            next_tok = self._tokens[self._pos + 1]
            if next_tok.type in ("AFTER", "BEFORE"):
                return self._parse_temporal()

        # Existence: field exists
        if tok.type == "IDENT" and self._pos + 1 < len(self._tokens):
            next_tok = self._tokens[self._pos + 1]
            if next_tok.type == "EXISTS":
                return self._parse_exists()

        # Comparison / membership / string ops
        return self._parse_comparison()

    def _parse_temporal(self) -> Condition:
        field_tok = self._advance()
        op_tok = self._advance()
        value_tok = self._advance()

        field = field_tok.value
        raw_value = self._strip_quotes(value_tok.value)
        dt = datetime.fromisoformat(raw_value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        op = (
            ComparisonOperator.GTE
            if op_tok.type == "AFTER"
            else ComparisonOperator.LTE
        )
        return Condition(
            field=field,
            operator=op,
            value=dt.isoformat(),
            condition_type=ConditionType.TEMPORAL,
        )

    def _parse_exists(self) -> Condition:
        field_tok = self._advance()
        self._advance()  # 'exists' keyword
        return Condition(
            field=field_tok.value,
            operator=ComparisonOperator.EQ,
            value="__exists__",
            condition_type=ConditionType.EXISTS,
        )

    def _parse_comparison(self) -> Condition:
        field_tok = self._advance()

        # Check for membership: in [...] / not_in [...]
        if self._peek() and self._peek().type in ("IN", "NOT_IN"):
            op_tok = self._advance()
            self._expect("LBRACKET")
            values = self._parse_value_list()
            self._expect("RBRACKET")
            op = (
                ComparisonOperator.IN
                if op_tok.type == "IN"
                else ComparisonOperator.NOT_IN
            )
            return Condition(field=field_tok.value, operator=op, value=values)

        # Check for string ops
        if self._peek() and self._peek().type in (
            "CONTAINS",
            "STARTS_WITH",
            "ENDS_WITH",
        ):
            op_tok = self._advance()
            value_tok = self._advance()
            op_map = {
                "CONTAINS": ComparisonOperator.CONTAINS,
                "STARTS_WITH": ComparisonOperator.STARTS_WITH,
                "ENDS_WITH": ComparisonOperator.ENDS_WITH,
            }
            return Condition(
                field=field_tok.value,
                operator=op_map[op_tok.type],
                value=self._strip_quotes(value_tok.value),
            )

        # Standard comparison
        op_tok = self._advance()
        value_tok = self._advance()
        op_map = {
            "EQ": ComparisonOperator.EQ,
            "NEQ": ComparisonOperator.NEQ,
            "GT": ComparisonOperator.GT,
            "GTE": ComparisonOperator.GTE,
            "LT": ComparisonOperator.LT,
            "LTE": ComparisonOperator.LTE,
            "MATCHES": ComparisonOperator.MATCHES,
            "NOT_MATCHES": ComparisonOperator.NOT_MATCHES,
        }
        raw_value = self._strip_quotes(value_tok.value)
        try:
            parsed_value = float(raw_value)
        except ValueError:
            parsed_value = raw_value

        return Condition(
            field=field_tok.value, operator=op_map[op_tok.type], value=parsed_value
        )

    def _parse_value_list(self) -> list[Any]:
        values: list[Any] = []
        tok = self._peek()
        if tok and tok.type in ("STRING", "NUMBER", "IDENT"):
            values.append(self._parse_list_value())
            while self._peek() and self._peek().type == "COMMA":
                self._advance()
                values.append(self._parse_list_value())
        return values

    def _parse_list_value(self) -> Any:
        tok = self._advance()
        if tok.type == "STRING":
            return self._strip_quotes(tok.value)
        if tok.type == "NUMBER":
            try:
                return int(tok.value)
            except ValueError:
                return float(tok.value)
        return tok.value

    @staticmethod
    def _strip_quotes(s: str) -> str:
        if (s.startswith("'") and s.endswith("'")) or (
            s.startswith('"') and s.endswith('"')
        ):
            return s[1:-1]
        return s


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_condition(expression: str) -> Condition | CompoundCondition:
    """Parse a condition expression string into a Condition tree.

    Examples::

        parse_condition("risk_score >= 0.9")
        parse_condition("risk_score >= 0.8 AND confidence < 0.5")
        parse_condition("(risk_level == critical OR risk_level == severe) AND confidence > 0.7")
        parse_condition("source_type =~ 'web_.*'")
        parse_condition("risk_level in [critical, severe, high]")
        parse_condition("model_name exists")
    """
    if not expression or not expression.strip():
        raise ConditionParseError("Empty condition expression")
    tokens = _tokenize(expression)
    if not tokens:
        raise ConditionParseError(f"No tokens found in expression: {expression!r}")
    parser = _Parser(tokens)
    return parser.parse()
