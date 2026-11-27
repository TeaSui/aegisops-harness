"""The engine is layered (scripts/aidlc_lib/): a layer imports only the ones below it, so no import cycle can form."""
import pathlib
import re
import unittest

LIB = pathlib.Path(__file__).resolve().parent.parent / 'plugins' / 'aegisops-harness' / 'scripts' / 'aidlc_lib'
ORDER = ['core', 'parsers', 'graph', 'model', 'gates', 'api', 'commands']
MAX_LINES = 1000


class EngineLayersTest(unittest.TestCase):
    def test_a_layer_imports_only_the_layers_below_it(self):
        for position, name in enumerate(ORDER):
            text = (LIB / f'{name}.py').read_text()
            imported = re.findall(r'^from aidlc_lib\.(\w+) import', text, re.M)
            self.assertEqual(imported, ORDER[:position], f'{name}.py imports {imported}')

    def test_no_module_grows_back_into_a_monolith(self):
        for path in sorted(LIB.glob('*.py')):
            self.assertLessEqual(len(path.read_text().splitlines()), MAX_LINES,
                                 f'{path.name} is over {MAX_LINES} lines: split it by concern')

    def test_every_layer_is_listed(self):
        self.assertEqual(sorted(p.stem for p in LIB.glob('*.py') if p.stem != '__init__'), sorted(ORDER))


if __name__ == '__main__':
    unittest.main()
