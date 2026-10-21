"""Controlli senza GTK sul collegamento fra sorgente importato e foglio stile."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ImportedSourceTests(unittest.TestCase):
    def test_css_theme_placeholders_are_resolved(self):
        tree = ast.parse((ROOT / 'tasto/app.py').read_text())
        names = {'theme', 'THEMES', 'THEME_ORDER', 'extra_css', 'FONTS', 'UI_SIZE'}
        nodes = [n for n in tree.body if
                 isinstance(n, ast.FunctionDef) and n.name in names or
                 isinstance(n, ast.Assign) and any(
                     isinstance(t, ast.Name) and t.id in names for t in n.targets)]
        namespace = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<theme definitions>', 'exec'), namespace)
        css = (ROOT / 'tasto/style.css').read_text()
        for name, theme in namespace['THEMES'].items():
            for _, font, scale in namespace['FONTS']:
                values = dict(theme, font=font, size=f'{14 * scale:.1f}',
                              ui=f"{namespace['UI_SIZE'] * scale:.1f}", uifont=font,
                              accent=theme['syn']['head'])
                resolved = css
                for key, value in values.items():
                    if isinstance(value, str):
                        resolved = resolved.replace(f'@{key}@', value)
                self.assertFalse(re.findall(r'@[a-z]+@', resolved), name)
                self.assertIn(f'.sq-{name}', namespace['extra_css']())

    def test_stylesheet_loaded_relative_to_module(self):
        source = (ROOT / 'tasto/app.py').read_text()
        self.assertIn('Path(__file__).with_name("style.css")', source)
        self.assertIn('APP = "Tasto"', source)
        self.assertIn('GLib.get_user_config_dir(), "tasto"', source)
