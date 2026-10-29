"""Independent full-fab checks, including an analytically solvable DES case."""
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('factory_model', ROOT/'week7/factory/model.py')
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class FullFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads((ROOT/'week7/factory/factory-data.json').read_text(encoding='utf-8'))

    def test_scope_and_source_counts(self):
        d = self.d
        self.assertEqual(len(d['vehicles']), 500)
        self.assertEqual(len(d['equipment']), 1116)
        self.assertEqual(sum(e['production'] for e in d['equipment']), 1068)
        self.assertEqual(len({r[3] for r in d['rails']}), 43)
        self.assertEqual(d['metrics']['initial_wip'], 2156)
        self.assertEqual(d['metrics']['vehicles_used'], 500)
        self.assertEqual(len(d['metrics']['bays_used']), 40)
        self.assertEqual(len(d['recipes']), 10)
        self.assertEqual(len({l['name'] for l in d['lots']}), len(d['lots']))

    def test_exact_directed_path_geometry(self):
        d = self.d
        edges = {(r[0], r[1]) for r in d['rails']}
        for s, t, nodes, length in d['paths']:
            a, b = d['spots'][s], d['spots'][t]
            points = [a[2:4]] + [d['nodes'][i] for i in nodes] + [b[2:4]]
            actual = sum(sum(abs(x-y) for x, y in zip(p, q)) for p, q in zip(points, points[1:]))
            self.assertAlmostEqual(actual, length, places=7)
            for u, v in zip(nodes, nodes[1:]):
                self.assertIn((u, v), edges)
            if nodes:
                self.assertEqual(nodes[0], d['rails'][a[0]][1])
                self.assertEqual(nodes[-1], d['rails'][b[0]][0])
            else:
                # Direct path either follows the same rail forward or has zero length.
                self.assertTrue(length < 1e-8 or (a[0] == b[0] and b[1] >= a[1]))

    def test_vehicle_exclusivity_location_and_travel_time(self):
        d = self.d
        for vi, vehicle in enumerate(d['vehicles']):
            end, location = 0., vehicle['initial']
            for idx in vehicle['trips']:
                v = d['visits'][idx]
                self.assertEqual(v['vehicle'], vi)
                self.assertGreaterEqual(v['dispatch']+1e-8, end)
                empty, loaded = d['paths'][v['empty']], d['paths'][v['loaded']]
                self.assertEqual(empty[0], location)
                self.assertEqual(empty[1], loaded[0])
                self.assertEqual(loaded[0], d['equipment'][v['source']]['spot'])
                self.assertEqual(loaded[1], d['equipment'][v['target']]['spot'])
                self.assertAlmostEqual((v['pickup']-v['dispatch'])*d['config']['speed'], empty[3], places=7)
                self.assertAlmostEqual((v['arrive']-v['depart'])*d['config']['speed'], loaded[3], places=7)
                self.assertAlmostEqual(v['depart']-v['pickup'], d['config']['load'])
                self.assertAlmostEqual(v['delivered']-v['arrive'], d['config']['load'])
                location, end = loaded[1], v['delivered']

    def test_processing_exclusivity_compatibility_and_fcfs(self):
        d, jobs = self.d, defaultdict(list)
        for v in d['visits']:
            if v['duration'] > 0:
                lot = d['lots'][v['lot']]
                op = d['recipes'][lot['product']][v['op']]
                self.assertEqual(op['group'], d['equipment'][v['target']]['group'])
            if v['start'] is not None and v['duration'] > 0:
                self.assertGreaterEqual(v['start']+1e-8, v['delivered'])
                self.assertAlmostEqual(v['end']-v['start'], v['duration'])
                jobs[v['target']].append(v)
        for rows in jobs.values():
            rows.sort(key=lambda v: v['start'])
            for a, b in zip(rows, rows[1:]):
                self.assertGreaterEqual(b['start']+1e-8, a['end'])
                self.assertGreaterEqual(b['delivered']+1e-8, a['delivered'])

    def test_lot_precedence_including_delay_steps(self):
        d = self.d
        for li, lot in enumerate(d['lots']):
            rows = [(d['visits'][i]['op'], 'visit', d['visits'][i]) for i in lot['visits']]
            rows += [(d['delays'][i]['op'], 'delay', d['delays'][i]) for i in lot['delays']]
            rows.sort()
            previous_end = lot['release']
            source = lot['origin']
            for op, kind, row in rows:
                self.assertEqual(row['lot'], li)
                self.assertEqual(op, lot['start'])
                lot = {**lot, 'start': op+1}
                start = row['request'] if kind == 'visit' else row['start']
                self.assertAlmostEqual(start, previous_end)
                self.assertEqual(row['source'], source)
                if kind == 'visit':
                    previous_end, source = row['end'], row['target']
                else:
                    previous_end = row['end']
                if previous_end is None:
                    self.assertEqual(op, rows[-1][0])

    def test_small_hand_calculated_queue(self):
        net = model.Network.__new__(model.Network)
        net.nodes = [[0., 0.], [9., 0.]]
        net.rails = [[0, 1, 9., 'A'], [1, 0, 9., 'A']]
        net.reverse = [[(1, 9.)], [(0, 9.)]]
        net.spots = [[0, 0., 0., 0., 'S'], [0, 9., 9., 0., 'M'], [1, 0., 9., 0., 'T']]
        net.trees, net.paths, net.path_index = {}, [], {}
        equipment = [dict(spot=i, bay='A') for i in [0, 1, 1]]
        groups = {'M': [1], 'COMPLETE': [2]}
        recipes = [[dict(group='M', duration=2.)]]
        vehicles = [dict(initial=0)]
        lots = [dict(product=0, start=0, origin=0, release=0., source='WIP', visits=[], delays=[]) for _ in range(2)]
        result = model.simulate(net, equipment, groups, recipes, vehicles, lots, horizon=10)
        a, b = result['visits'][:2]
        self.assertAlmostEqual(a['delivered'], .6)
        self.assertAlmostEqual(a['start'], .6)
        self.assertAlmostEqual(a['end'], 2.6)
        self.assertAlmostEqual(b['delivered'], 1.3)
        self.assertAlmostEqual(b['start'], 2.6)
        self.assertAlmostEqual(b['end'], 4.6)
        self.assertAlmostEqual(lots[0]['completed'], 3.1)
        self.assertAlmostEqual(lots[1]['completed'], 5.1)


if __name__ == '__main__':
    unittest.main()
