import tempfile
from pathlib import Path
import unittest
from tasto.library import markdown_files, recent_in_folder, remember_file


class LibraryTests(unittest.TestCase):
    def test_lists_markdown_alphabetically_without_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ('zeta.md', 'Alfa.MD', 'beta.markdown', 'altro.txt'):
                (folder / name).write_text('testo', encoding='utf-8')
            (folder / 'cartella.md').mkdir()
            self.assertEqual([p.name for p in markdown_files(folder)], ['Alfa.MD', 'beta.markdown', 'zeta.md'])

    def test_recent_files_are_existing_unique_and_from_selected_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            other = folder / 'altra'
            other.mkdir()
            for path in (folder/'uno.md', folder/'due.md', other/'tre.md'):
                path.write_text('testo', encoding='utf-8')
            history = [str(other/'tre.md'), str(folder/'assente.md'), str(folder/'due.md'),
                       str(folder/'due.md'), str(folder/'uno.md'), None]
            self.assertEqual([p.name for p in recent_in_folder(folder, history)], ['due.md', 'uno.md'])

    def test_reopening_moves_file_to_front_and_caps_history(self):
        history = ['/tmp/alfa.md', '/tmp/beta.md', '/tmp/gamma.md']
        self.assertEqual(remember_file(history, '/tmp/beta.md', limit=2), ['/tmp/beta.md', '/tmp/alfa.md'])

    def test_missing_folder_reports_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                markdown_files(Path(temporary)/'assente')

    def test_recent_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary)/f'{n}.md' for n in range(8)]
            for path in paths:
                path.write_text('testo', encoding='utf-8')
            self.assertEqual(recent_in_folder(temporary, list(map(str, paths))), paths[:5])
