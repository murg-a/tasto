"""Trasformazioni Markdown, indipendenti da GTK e verificabili senza display."""
import re
from .preview import LIST_PREFIX, parse


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


def list_newline_edit(text, start, end):
    """Restituisce (inizio, fine, testo) per Invio in lista, oppure None.

    Una voce vuota termina l'elenco. Selezioni su più righe, prefissi selezionati
    e blocchi di codice mantengono il comportamento nativo dell'editor.
    """
    first = text.rfind('\n', 0, start) + 1
    last = text.find('\n', start)
    if last < 0:
        last = len(text)
    if end > last:
        return None
    # Solo classificazione dei blocchi: nessuna analisi della sintassi inline.
    line = parse(text[:last], inline=False)[-1]
    if not line.list_prefix or start < first + len(line.list_prefix):
        return None
    prefix = LIST_PREFIX.match(line.text)
    content = text[first + prefix.end():start] + text[end:last]
    if not content.strip():
        return first, last, prefix['indent']
    marker = prefix['marker']
    if marker[0].isdigit():
        number = str(int(marker[:-1]) + 1)
        if marker.startswith('0'):
            number = number.zfill(len(marker) - 1)
        marker = number + marker[-1]
    return start, end, '\n' + prefix['indent'] + marker + (prefix['space'] or ' ')
