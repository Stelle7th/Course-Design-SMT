"""Check the plant overview independently of event simulation output."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('build_viewer', ROOT/'week7/visualization/build_viewer.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class FactoryViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = builder.build_factory_context(ROOT)

    def test_factory_counts_and_unique_equipment(self):
        self.assertEqual(self.data['counts'], {'equipment': 1116, 'production': 1068,
                                             'fixed_amhs': 48, 'bays': 43})
        self.assertEqual(len({e['name'] for e in self.data['equipment']}), 1116)
        self.assertEqual(len(self.data['bays']), 43)

    def test_bay_envelopes_and_simulation_scope(self):
        bays = {b['name']: b for b in self.data['bays']}
        self.assertEqual({b['name'] for b in bays.values() if b['simulated']}, {'A2', 'A3'})
        self.assertEqual(sum(e['bay'] in {'A2', 'A3'} and e['kind']=='production'
                             for e in self.data['equipment']), 48)
        self.assertEqual(sum(e['bay'] in {'A2', 'A3'} for e in self.data['equipment']), 50)
        self.assertEqual(bays['InterBay2']['count'], 0)
        self.assertGreater(bays['InterBay2']['x1']-bays['InterBay2']['x0'], 300)
        for e in self.data['equipment']:
            box = bays[e['bay']]
            self.assertLessEqual(box['x0'], e['x']-e['width']/2)
            self.assertGreaterEqual(box['x1'], e['x']+e['width']/2)
            self.assertLessEqual(box['y0'], e['y']-e['height']/2)
            self.assertGreaterEqual(box['y1'], e['y']+e['height']/2)


if __name__ == '__main__':
    unittest.main()
