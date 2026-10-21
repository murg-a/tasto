"""Decorazioni Live Preview: offset Unicode, nessuna modifica alla sorgente.

Sottoinsieme intenzionale di Markdown; HTML limitato a tag inline accoppiati.
Le costruzioni non riconosciute restano leggibili come sorgente.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Line:
    text: str
    spans: list = field(default_factory=list)
    hidden: list = field(default_factory=list)
    heading: tuple | None = None
    block: tuple | None = None


INLINE = re.compile(
    r'(?P<escape>\\[\\`*_{}\[\]()#+.!>~-])'
    r'|(?P<code>(?P<ticks>`+)(?!`)(?P<code_text>.+?)(?<!`)(?P=ticks)(?!`))'
    r'|(?P<link>(?<!!)\[(?P<link_text>[^\]\n]+)\]\([^)\n]+\))'
    r'|(?P<html><(?P<html_tag>b|strong|i|em|u|s|del|code)>(?P<html_text>.+?)</(?P=html_tag)>)'
    r'|(?P<strong>(?P<strong_mark>\*\*|__)(?=\S)(?P<strong_text>.+?)(?<=\S)(?P=strong_mark))'
    r'|(?P<strike>~~(?=\S)(?P<strike_text>.+?)(?<=\S)~~)'
    r'|(?P<italic>(?<![\w*_])(?P<italic_mark>[*_])(?=\S)(?P<italic_text>.+?)(?<=\S)(?P=italic_mark)(?!\w))', re.I)


def parse_inline(line, start=0, end=None, depth=0):
    end = len(line.text) if end is None else end
    if depth >= 24:
        return
    for match in INLINE.finditer(line.text, start, end):
        kind = match.lastgroup
        if kind == 'escape':
            line.hidden.append((match.start(), match.start() + 1))
            continue
        if kind == 'html':
            content = 'html_text'
            style = {'b': 'bold', 'strong': 'bold', 'i': 'ital', 'em': 'ital',
                     'u': 'underline', 's': 'strike', 'del': 'strike', 'code': 'code'}[match['html_tag'].lower()]
        else:
            content = kind + '_text'
            style = {'code': 'code', 'link': 'linktext', 'strong': 'bold',
                     'strike': 'strike', 'italic': 'ital'}[kind]
        a, b = match.span(content)
        line.spans.append((style, a, b))
        line.hidden.extend(((match.start(), a), (b, match.end())))
        if style != 'code':
            parse_inline(line, a, b, depth + 1)


def parse(text):
    lines = [Line(value) for value in text.split('\n')]
    fence = None
    for n, line in enumerate(lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line.text)
        if fence is not None:
            line.spans.append(('code', 0, len(line.text)))
            if marker and marker[1][0] == fence[1] and len(marker[1]) >= fence[2] and not marker[2].strip():
                line.hidden.append((0, len(line.text)))
                for member in lines[fence[0]:n + 1]:
                    member.block = (fence[0], n)
                fence = None
            continue
        if marker and not (marker[1][0] == '`' and '`' in marker[2]):
            fence = (n, marker[1][0], len(marker[1]))
            line.spans.append(('code', 0, len(line.text)))
            line.hidden.append((0, len(line.text)))
            continue
        heading = re.match(r'^ {0,3}(#{1,6})[ \t]+(.+?)\s*$', line.text)
        start = 0
        if heading:
            level = len(heading[1])
            line.heading = (level, heading[2], n)
            line.spans.append((f'h{level}', 0, len(line.text)))
            line.hidden.append((0, heading.start(2)))
            start = heading.start(2)
        if line.text.startswith(('    ', '\t')):
            line.spans.append(('code', 0, len(line.text)))
        else:
            parse_inline(line, start)
            for ref in re.finditer(r"\[\^\d+\](?!:)", line.text):
                line.spans.append(("footnote", *ref.span()))
    if fence:
        for member in lines[fence[0]:]:
            member.block = (fence[0], len(lines) - 1)
    return lines


def active_lines(lines, first, last):
    """La selezione rivela anche gli eventuali blocchi di codice attraversati."""
    active = set(range(first, last + 1))
    for n in tuple(active):
        if 0 <= n < len(lines) and lines[n].block:
            a, b = lines[n].block
            active.update(range(a, b + 1))
    return active
