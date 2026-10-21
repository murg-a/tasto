"""Markdown block boundaries, independent of GTK."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    text: str


def blocks(text):
    """Blank lines delimit blocks, except within fenced code."""
    result = []
    start = None
    offset = 0
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
        if start is None and line.strip():
            start = offset
        if marker:
            run, suffix = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not suffix.strip():
                fence = None
        if not line.strip() and fence is None and start is not None:
            result.append(Block(start, offset, text[start:offset]))
            start = None
        offset += len(line)
    if start is not None:
        result.append(Block(start, len(text), text[start:]))
    return result


def insert_block(text, offset, content):
    """Insert at the exact character position, separating the resulting blocks."""
    offset = max(0, min(offset, len(text)))
    left, right = text[:offset], text[offset:]
    before = '' if not left or left.endswith('\n\n') else '\n' if left.endswith('\n') else '\n\n'
    body = content.rstrip('\r\n')
    after = '' if not right or right.startswith('\n\n') else '\n' if right.startswith('\n') else '\n\n'
    insertion = before + body + after
    return left + insertion + right, offset + len(insertion)
