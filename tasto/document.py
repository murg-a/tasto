"""Operazioni sul documento indipendenti dall'interfaccia grafica."""
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class Document:
    text: str = ''
    path: Path | None = None
    saved_text: str = ''

    @property
    def modified(self):
        return self.text != self.saved_text

    @property
    def counts(self):
        return len(self.text), len(self.text.split())

    @property
    def headings(self):
        return [(len(m.group(1)), m.group(2), m.start())
                for m in re.finditer(r'^(#{1,5})[ \t]+(.+)$', self.text, re.MULTILINE)]

    def open(self, path):
        path = Path(path)
        text = path.read_text(encoding='utf-8')
        self.text = self.saved_text = text
        self.path = path

    def save(self, path=None):
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError('Scegli prima un file.')
        # Sostituzione atomica: un errore di scrittura non tronca il documento.
        import os
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix='.tasto-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(self.text)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.path = target
        self.saved_text = self.text
