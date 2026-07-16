"""Small bounded S-expression reader; it never invokes KiCad or a shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SExpression:
    value: str | tuple[SExpression, ...]

    @property
    def atom(self) -> str | None:
        return self.value if isinstance(self.value, str) else None

    @property
    def children(self) -> tuple[SExpression, ...]:
        return self.value if isinstance(self.value, tuple) else ()


def parse_sexpression(content: bytes) -> SExpression:
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("sexpression_too_large")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("sexpression_not_utf8") from error
    tokens = _tokenize(text)
    if len(tokens) > 250_000:
        raise ValueError("sexpression_token_limit")
    stack: list[list[SExpression]] = []
    root: SExpression | None = None
    for lexeme in tokens:
        if lexeme == "(":
            if len(stack) >= 128:
                raise ValueError("sexpression_depth_limit")
            stack.append([])
        elif lexeme == ")":
            if not stack:
                raise ValueError("sexpression_unbalanced")
            expression = SExpression(tuple(stack.pop()))
            if stack:
                stack[-1].append(expression)
            elif root is None:
                root = expression
            else:
                raise ValueError("sexpression_multiple_roots")
        else:
            if not stack:
                raise ValueError("sexpression_atom_outside_root")
            stack[-1].append(SExpression(lexeme))
    if stack or root is None:
        raise ValueError("sexpression_unbalanced")
    return root


def head(expression: SExpression) -> str | None:
    children = expression.children
    return children[0].atom if children else None


def child_lists(expression: SExpression, name: str) -> tuple[SExpression, ...]:
    return tuple(child for child in expression.children[1:] if head(child) == name)


def child_value(expression: SExpression, name: str) -> str | None:
    matches = child_lists(expression, name)
    if not matches or len(matches[0].children) < 2:
        return None
    return matches[0].children[1].atom


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            index += 1
            value: list[str] = []
            while index < len(text):
                char = text[index]
                if char == '"':
                    index += 1
                    break
                if char == "\\":
                    index += 1
                    if index >= len(text):
                        raise ValueError("sexpression_invalid_escape")
                    escapes = {"n": "\n", "r": "\r", "t": "\t"}
                    value.append(escapes.get(text[index], text[index]))
                    index += 1
                    continue
                value.append(char)
                index += 1
            else:
                raise ValueError("sexpression_unterminated_string")
            tokens.append("".join(value))
            continue
        start = index
        while index < len(text) and not text[index].isspace() and text[index] not in "()":
            index += 1
        tokens.append(text[start:index])
    return tokens
