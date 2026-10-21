"""Note Markdown standard: richiami [^1] e definizioni [^1]: testo."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Footnote:
    number: str
    content: str
    start: int
    end: int


def notes(text):
    result = []
    lines = text.splitlines(keepends=True)
    offset = index = 0
    fence = None
    while index < len(lines):
        line = lines[index]
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
        match = re.match(r'^\[\^(\d+)\]:[ \t]*(.*?)(?:\r?\n)?$', line) if fence is None else None
        if match:
            start = offset
            content = [match[2]]
            offset += len(line)
            index += 1
            while index < len(lines) and lines[index].startswith(('    ', '\t')):
                continuation = lines[index]
                content.append(continuation[1 if continuation.startswith('\t') else 4:].rstrip('\r\n'))
                offset += len(continuation)
                index += 1
            result.append(Footnote(match[1], '\n'.join(content), start, offset))
            continue
        offset += len(line)
        index += 1
    return result


def definition(number, content):
    lines = content.split('\n')
    return f'[^{number}]: {lines[0]}' + ''.join('\n    ' + line for line in lines[1:]) + '\n'


def add_note(text, cursor):
    # Anche i richiami senza definizione riservano il proprio numero.
    used = [int(n) for n in re.findall(r'\[\^(\d+)\]', text)]
    number = str(max(used, default=0) + 1)
    reference = f'[^{number}]'
    updated = text[:cursor] + reference + text[cursor:]
    separator = '' if updated.endswith('\n\n') else '\n' if updated.endswith('\n') else '\n\n'
    return updated + separator + definition(number, ''), cursor + len(reference), number


def update_note(text, number, content):
    found = [note for note in notes(text) if note.number == str(number)]
    if len(found) != 1:
        raise ValueError('La nota è assente o il numero è duplicato nel documento.')
    note = found[0]
    return text[:note.start] + definition(note.number, content) + text[note.end:]
