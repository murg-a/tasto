"""Elenco Markdown e cronologia della schermata iniziale, senza dipendenze GTK."""
from pathlib import Path

SUFFIXES = {'.md', '.markdown'}


def markdown_files(folder):
    folder = Path(folder).expanduser().absolute()
    return sorted((path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in SUFFIXES),
                  key=lambda path: (path.name.casefold(), path.name))


def recent_in_folder(folder, history, limit=5):
    folder = Path(folder).expanduser().resolve()
    result = []
    seen = set()
    for entry in history:
        if not isinstance(entry, str):
            continue
        path = Path(entry).expanduser().absolute()
        if path in seen or path.parent.resolve() != folder:
            continue
        if path.is_file() and path.suffix.lower() in SUFFIXES:
            result.append(path)
            seen.add(path)
            if len(result) >= limit:
                break
    return result


def remember_file(history, path, limit=100):
    path = str(Path(path).expanduser().absolute())
    return [path] + [item for item in history if isinstance(item, str) and item != path][:limit-1]
