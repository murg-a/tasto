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


@dataclass(frozen=True)
class Reference:
    number: str
    start: int
    end: int


def references(text):
    """Richiami nel corpo, escludendo definizioni, codice e testo escapato."""
    definitions = notes(text)
    pattern = re.compile(r'\[\^(\d+)\]')
    result = []
    fence = None
    offset = 0
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            run = marker[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            offset += len(line)
            continue
        if fence is None:
            code = [m.span() for m in re.finditer(r'(`+).*?\1', line)]
            for match in pattern.finditer(line):
                position = offset + match.start()
                escaped = len(line[:match.start()]) - len(line[:match.start()].rstrip('\\'))
                if (not escaped % 2 and not any(a <= match.start() < b for a, b in code)
                        and not any(note.start <= position < note.end for note in definitions)):
                    result.append(Reference(match[1], position, offset + match.end()))
        offset += len(line)
    return result


def reference_offset(text, number):
    return next((ref.start for ref in references(text) if ref.number == str(number)), None)


def apply_edits(text, edits, cursor):
    """Applica sostituzioni non sovrapposte mantenendo il cursore sul contenuto."""
    edits = sorted(edits)
    shift = 0
    mapped = None
    for start, end, value in edits:
        if cursor >= end:
            shift += len(value) - (end - start)
        elif cursor > start:
            mapped = start + shift + min(cursor - start, len(value))
            break
        else:
            break
    if mapped is None:
        mapped = cursor + shift
    for start, end, value in reversed(edits):
        text = text[:start] + value + text[end:]
    return text, mapped


def synchronize_notes(text, cursor=0, removed_references=(), removed_definitions=()):
    """Rinumera per prima occorrenza senza cancellare note importate orfane.

    La rimozione è esplicita: è autorizzata solo dalla cancellazione completa
    di un richiamo/definizione durante un'azione dell'utente.
    """
    entries = notes(text)
    # Definizioni duplicate sono ambigue: non rischiare di associarle al testo sbagliato.
    if len({note.number for note in entries}) != len(entries):
        return text, cursor, {ref.number: ref.number for ref in references(text)}
    refs = references(text)
    live = {ref.number for ref in refs}
    drop_definitions = set(removed_definitions) | (set(removed_references) - live)
    drop_references = set(removed_definitions)
    kept_refs = [ref for ref in refs if ref.number not in drop_references]
    kept_notes = [note for note in entries if note.number not in drop_definitions]
    order = list(dict.fromkeys([ref.number for ref in kept_refs] + [note.number for note in kept_notes]))
    mapping = {old: str(index) for index, old in enumerate(order, 1)}
    edits = []
    for ref in refs:
        if ref.number in drop_references:
            edits.append((ref.start, ref.end, ''))
        elif mapping[ref.number] != ref.number:
            edits.append((ref.start, ref.end, f'[^{mapping[ref.number]}]'))
    for note in entries:
        if note.number in drop_definitions:
            edits.append((note.start, note.end, ''))
        elif mapping[note.number] != note.number:
            edits.append((note.start, note.start + len(note.number) + 3, f'[^{mapping[note.number]}]'))
    updated, cursor = apply_edits(text, edits, cursor)
    return updated, cursor, mapping


def reconcile_notes(before, after, cursor, deleted_references=(), deleted_definitions=()):
    """Sincronizza una singola azione completata (anche incolla/sostituisci)."""
    if "[^" not in before and "[^" not in after:
        return after, cursor, {}
    first = 0
    limit = min(len(before), len(after))
    while first < limit and before[first] == after[first]:
        first += 1
    tail = 0
    while tail < limit - first and before[-tail-1] == after[-tail-1]:
        tail += 1
    end = len(before) - tail
    old_refs = references(before)
    live_refs = {ref.number for ref in references(after)}
    if any(ref.number not in live_refs and ref.number not in deleted_references and not (first <= ref.start and ref.end <= end) for ref in old_refs):
        # Modifica parziale del marcatore: non cancellare né rinumerare mentre
        # l'utente sta ancora correggendo la sintassi.
        return after, cursor, {}
    removed_refs = set(deleted_references) | {ref.number for ref in old_refs if first <= ref.start and ref.end <= end}
    live_definitions = {note.number for note in notes(after)}
    removed_defs = set(deleted_definitions) - live_definitions
    for note in notes(before):
        content_end = note.start + len(before[note.start:note.end].rstrip('\r\n'))
        if (note.number not in live_definitions and first <= note.start + len(note.number) + 3
                and content_end <= end and len(before) - len(after) >= content_end - note.start):
            removed_defs.add(note.number)
    return synchronize_notes(after, cursor, removed_refs, removed_defs)
