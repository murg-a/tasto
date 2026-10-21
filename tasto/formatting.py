"""Trasformazioni Markdown, indipendenti da GTK e verificabili senza display."""
import re


def format_edit(text, start, end, command):
    """Restituisce intervallo da sostituire, testo e selezione relativa al risultato."""
    wrappers = {'bold': ('**', '**'), 'italic': ('_', '_'),
                'underline': ('<u>', '</u>'), 'strike': ('~~', '~~')}
    if command in wrappers:
        left, right = wrappers[command]
        selected = text[start:end]
        if selected.startswith(left) and selected.endswith(right) and len(selected) >= len(left + right):
            content = selected[len(left):-len(right)]
            return start, end, content, 0, len(content)
        return start, end, left + selected + right, len(left), len(left) + len(selected)
    first = text.rfind('\n', 0, start) + 1
    # Una selezione che termina all'inizio della riga successiva non la include.
    last_position = end - 1 if end > start and text[end-1:end] == '\n' else end
    last = text.find('\n', last_position)
    if last < 0:
        last = len(text)
    lines = text[first:last].split('\n')
    result = []
    for index, line in enumerate(lines, 1):
        if command in ('bullet', 'number'):
            match = re.match(r'^(\s*)(?:[-+*] |\d+[.)] )?(.*)$', line)
            indent, content = match.groups()
            result.append(indent + ('- ' if command == 'bullet' else f'{index}. ') + content)
        elif command == 'indent':
            result.append('    ' + line)
        elif command == 'outdent':
            result.append(re.sub(r'^(?: {1,4}|\t)', '', line))
        else:
            raise ValueError(f'Comando sconosciuto: {command}')
    replacement = '\n'.join(result)
    if start == end:
        # Cursore prima del contenuto della riga, dopo il nuovo prefisso.
        offset = max(0, min(len(replacement), start - first + len(replacement) - (last-first)))
        return first, last, replacement, offset, offset
    return first, last, replacement, 0, len(replacement)
