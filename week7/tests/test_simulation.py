"""Independent invariants and an analytically solvable queueing example.

Uses only the Python standard library. Run from the repository root:
    python -m unittest discover -s week7/tests -v
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'week7' / 'simulation' / 'results.json'
ENGINE = ROOT / 'week7' / 'simulation' / 'engine.py'


class TinyRouter:
    """Three collinear ports; all directions take their Manhattan distance."""
    def __init__(self):
        self.positions = {'S': (0, 0), 'M': (1, 0), 'T': (2, 0)}
        self.paths = {}

    def route(self, source, target):
        key = f'{source}>{target}'
        a, b = self.positions[source], self.positions[target]
        self.paths[key] = {'distance_raw': abs(a[0] - b[0]) + abs(a[1] - b[1]),
                           'points': [list(a), list(b)], 'source': source, 'target': target}
        return key


def assert_nonoverlapping(testcase, intervals, description):
    intervals = sorted((a, b) for a, b in intervals if b - a > 1e-8)
    for (a0, a1), (b0, b1) in zip(intervals, intervals[1:]):
        testcase.assertLessEqual(a1, b0 + 1e-6, f'{description}: {(a0, a1)} vs {(b0, b1)}')


class SimulationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RESULTS.is_file():
            raise RuntimeError('Run week7/simulation/engine.py before these tests.')
        cls.data = json.loads(RESULTS.read_text(encoding='utf-8'))
        cls.original = json.loads((ROOT / 'week6/交互展示/milp-data.json').read_text(encoding='utf-8'))
        spec = importlib.util.spec_from_file_location('week7_sim_engine_tested', ENGINE)
        cls.engine = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.engine
        spec.loader.exec_module(cls.engine)

    def cases(self):
        for scenario in self.data['scenarios']:
            for name in ('before', 'after'):
                yield scenario, name, scenario['cases'][name]

    def test_common_task_inputs_and_fixed_boundaries(self):
        for scenario in self.data['scenarios']:
            before = {t['task_id']: t for t in scenario['cases']['before']['tasks']}
            after = {t['task_id']: t for t in scenario['cases']['after']['tasks']}
            self.assertEqual(len(before), 560)
            self.assertEqual(before.keys(), after.keys())
            for key, task in before.items():
                for field in ('part', 'step', 'group', 'release', 'source', 'target', 'process_min', 'nominal_process_min'):
                    self.assertEqual(task[field], after[key][field], f'{key}: {field}')
                self.assertAlmostEqual(task['process_min'], task['nominal_process_min'] / .85, delta=1e-6)

    def test_task_completion_and_continuous_timelines(self):
        for scenario, name, case in self.cases():
            self.assertEqual(len(case['tasks']), 560)
            for task in case['tasks']:
                segments = task['timeline']
                self.assertTrue(segments)
                self.assertAlmostEqual(segments[0]['t0'], task['release'], places=6)
                for segment in segments:
                    self.assertGreaterEqual(segment['t1'] + 1e-8, segment['t0'])
                for previous, current in zip(segments, segments[1:]):
                    self.assertAlmostEqual(previous['t1'], current['t0'], places=6,
                                           msg=f"{scenario['id']}/{name}/{task['task_id']}")
                states = [s['state'] for s in segments]
                self.assertEqual(states.count('processing'), 1)
                processing = next(s for s in segments if s['state'] == 'processing')
                self.assertAlmostEqual(processing['t1'] - processing['t0'], task['process_min'], delta=2e-6)

    def test_equipment_compatibility_and_exclusive_processing(self):
        slots = {s['slot_name']: s for s in self.original['slots']}
        for scenario, name, case in self.cases():
            busy = {}
            for task in case['tasks']:
                self.assertIn(task['slot'], slots)
                group = slots[task['slot']]['original_group' if name == 'before' else 'optimized_group']
                self.assertEqual(task['group'], group)
                for segment in task['timeline']:
                    if segment['state'] == 'processing':
                        busy.setdefault(task['slot'], []).append((segment['t0'], segment['t1']))
            for slot, intervals in busy.items():
                assert_nonoverlapping(self, intervals, f'{scenario["id"]}/{name}/{slot}')

    def test_requests_vehicle_exclusivity_and_location_continuity(self):
        meta, paths = self.data['meta'], self.data['network']['paths']
        for scenario, name, case in self.cases():
            requests = case['requests']
            self.assertEqual(len(requests), 2 * len(case['tasks']))
            self.assertEqual(len({r['request_id'] for r in requests}), len(requests))
            # Requests are emitted in creation order. FCFS cannot assign a later
            # request strictly before an earlier request, irrespective of route.
            for earlier, later in zip(requests, requests[1:]):
                self.assertLessEqual(earlier['created_at'], later['created_at'] + 2e-6)
                self.assertLessEqual(earlier['assigned_at'], later['assigned_at'] + 2e-6)
            by_task, by_vehicle = {}, {}
            for request in requests:
                by_task.setdefault(request['task_id'], {})[request['phase']] = request
                by_vehicle.setdefault(request['vehicle_id'], []).append(request)
                self.assertLessEqual(request['created_at'], request['assigned_at'] + 2e-6)
                self.assertLessEqual(request['assigned_at'], request['pickup_at'] + 2e-6)
                self.assertLessEqual(request['pickup_at'], request['delivered_at'] + 2e-6)
                empty_duration = paths[request['empty_path']]['distance_raw'] / meta['speed_raw_per_min']
                loaded_duration = paths[request['path']]['distance_raw'] / meta['speed_raw_per_min']
                self.assertAlmostEqual(request['pickup_at'] - request['assigned_at'], empty_duration, delta=2e-6)
                self.assertAlmostEqual(request['delivered_at'] - request['pickup_at'],
                                       loaded_duration + meta['load_min'] + meta['unload_min'], delta=2e-6)
                self.assertEqual(request['path'], request['source'] + '>' + request['target'])
                self.assertEqual(request['empty_path'].split('>')[1], request['source'])
            for task in case['tasks']:
                incoming, outgoing = by_task[task['task_id']]['in'], by_task[task['task_id']]['out']
                self.assertEqual((incoming['source'], incoming['target']), (task['source'], task['slot']))
                self.assertEqual((outgoing['source'], outgoing['target']), (task['slot'], task['target']))
                self.assertAlmostEqual(incoming['created_at'], task['release'], delta=2e-6)
                process = next(p for p in task['timeline'] if p['state'] == 'processing')
                self.assertAlmostEqual(outgoing['created_at'], process['t1'], delta=2e-6)
                self.assertAlmostEqual(outgoing['delivered_at'], task['completed_at'], delta=2e-6)
            for vehicle in case['vehicles']:
                tasks = sorted(by_vehicle.get(vehicle['vehicle_id'], []), key=lambda r: r['assigned_at'])
                assert_nonoverlapping(self, [(r['assigned_at'], r['delivered_at']) for r in tasks], vehicle['vehicle_id'])
                location = vehicle['initial_equipment']
                for request in tasks:
                    self.assertEqual(request['empty_path'].split('>')[0], location)
                    location = request['target']
                legs = vehicle['legs']
                self.assertEqual(len(legs), 2 * len(tasks))
                assert_nonoverlapping(self, [(r['t0'], r['t1']) for r in legs], vehicle['vehicle_id'] + ' legs')
                previous_point = None
                for leg in legs:
                    path = paths[leg['path']]
                    self.assertAlmostEqual(leg['distance_raw'], path['distance_raw'], delta=2e-6)
                    self.assertAlmostEqual(leg['t1'] - leg['t0'], leg['distance_raw'] / meta['speed_raw_per_min'], delta=2e-6)
                    if previous_point is not None:
                        for a, b in zip(previous_point, path['points'][0]):
                            self.assertAlmostEqual(a, b, delta=2e-6)
                    previous_point = path['points'][-1]

    def test_reproducible_common_workload(self):
        first = self.engine.make_workload(self.original, seed=self.data['meta']['seed'])
        second = self.engine.make_workload(self.original, seed=self.data['meta']['seed'])
        self.assertEqual(first, second)
        manifest, assignments, selected, excluded = first
        self.assertEqual(len(manifest), 560)
        self.assertEqual(len({t['task_id'] for t in manifest}), 560)
        self.assertEqual(set(assignments['before']), set(assignments['after']))
        self.assertEqual(len(selected), 56)
        self.assertEqual(len(excluded), 3)
        for name in ('before', 'after'):
            totals = {}
            for task in manifest:
                key = (task['part'], task['step'])
                totals[key] = totals.get(key, 0) + 1
            self.assertEqual(set(totals.values()), {10})

    def test_route_distances_and_saved_allocations(self):
        paths = self.data['network']['paths']
        for key, path in paths.items():
            # Drawing points are rounded and divided by 1000; distance uses
            # unrounded Manhattan rail geometry. Allow at most 0.01 raw units.
            reconstructed = 1000 * sum(abs(a[0]-b[0]) + abs(a[1]-b[1])
                                       for a, b in zip(path['points'], path['points'][1:]))
            self.assertAlmostEqual(reconstructed, path['distance_raw'], delta=.01, msg=key)
        ops = {o['key']: o for o in self.original['operations']}
        selected = set(self.data['meta']['selected_operations'])
        excluded = set(self.data['meta']['excluded_operations'])
        self.assertEqual(selected | excluded, set(ops))
        self.assertFalse(selected & excluded)
        self.assertEqual(len(selected), 56)
        self.assertEqual(len(excluded), 3)
        for scenario, name, case in self.cases():
            for task in case['tasks']:
                op = ops[f"{task['part']}:{task['step']}"]
                incoming = [r for r in op[name] if r['direction'] == 'in']
                outgoing = [r for r in op[name] if r['direction'] == 'out']
                self.assertEqual(len(incoming), 1)
                self.assertEqual(len(outgoing), 1)
                self.assertEqual(task['slot'], incoming[0]['slot'])
                self.assertEqual(task['slot'], outgoing[0]['slot'])
                self.assertAlmostEqual(paths[task['source'] + '>' + task['slot']]['distance_raw'], incoming[0]['distance_raw'], delta=2e-6)
                self.assertAlmostEqual(paths[task['slot'] + '>' + task['target']]['distance_raw'], outgoing[0]['distance_raw'], delta=2e-6)

    def test_saved_planned_route_geometry_is_preserved(self):
        """Equal length is insufficient: loaded routes must keep plan topology."""
        network = self.original['network']
        paths = self.data['network']['paths']
        loaded_keys = {segment['path']
                       for _, _, case in self.cases()
                       for task in case['tasks']
                       for segment in task['timeline']
                       if segment['state'].startswith('loaded_')}
        self.assertTrue(loaded_keys)
        self.assertTrue(loaded_keys.issubset(network['paths']))
        router = self.engine.Router(ROOT)
        for key, planned in network['paths'].items():
            with self.subTest(path=key):
                actual = paths[key]
                self.assertEqual(actual['geometry_source'], 'saved_week6_plan')
                self.assertEqual(actual['node_ids'], planned['nodes'])
                expected = [planned['start']] + [network['nodes'][i] for i in planned['nodes']] + [planned['end']]
                expected = [point for i, point in enumerate(expected)
                            if i == 0 or point != expected[i-1]]
                self.assertEqual(len(actual['points']), len(expected))
                for current, previous in zip(actual['points'], expected):
                    self.assertAlmostEqual(current[0], previous[0], delta=.000006)
                    self.assertAlmostEqual(current[1], previous[1], delta=.000006)
                source, target = key.split('>')
                router.route(source, target)
                self.assertEqual(router.paths[key]['node_ids'], planned['nodes'])
                self.assertEqual(router.paths[key]['points'], actual['points'])

    def test_independent_metrics_recalculation(self):
        meta, paths = self.data['meta'], self.data['network']['paths']
        for scenario, name, case in self.cases():
            tasks, requests, metrics = case['tasks'], case['requests'], case['metrics']
            n, nr = len(tasks), len(requests)
            makespan = max(t['completed_at'] for t in tasks)
            self.assertAlmostEqual(metrics['makespan_min'], makespan, delta=2e-6)
            self.assertEqual(metrics['completed'], n)
            completed = sum(t['completed_at'] <= meta['horizon_min'] for t in tasks)
            self.assertEqual(metrics['completed_by_horizon'], completed)
            self.assertEqual(metrics['unfinished_by_horizon'], n - completed)
            cycles = [t['completed_at'] - t['release'] for t in tasks]
            durations = [r['delivered_at'] - r['created_at'] for r in requests]
            waits = sum(r['assigned_at'] - r['created_at'] for r in requests)
            machine_wait = sum(s['t1'] - s['t0'] for t in tasks for s in t['timeline'] if s['state'] == 'wait_equipment')
            process_time = sum(s['t1'] - s['t0'] for t in tasks for s in t['timeline'] if s['state'] == 'processing')
            busy_time = sum(r['delivered_at'] - r['assigned_at'] for r in requests)
            loaded_distance = sum(paths[r['path']]['distance_raw'] for r in requests)
            empty_distance = sum(paths[r['empty_path']]['distance_raw'] for r in requests)
            self.assertAlmostEqual(metrics['mean_region_time_min'], sum(cycles) / n, delta=2e-6)
            self.assertAlmostEqual(metrics['mean_transport_request_min'], sum(durations) / nr, delta=2e-6)
            self.assertAlmostEqual(metrics['p95_transport_request_min'], sorted(durations)[math.ceil(.95*nr)-1], delta=2e-6)
            self.assertAlmostEqual(metrics['mean_wait_vehicle_min'], waits / n, delta=2e-6)
            self.assertAlmostEqual(metrics['mean_wait_machine_min'], machine_wait / n, delta=2e-6)
            self.assertAlmostEqual(metrics['total_loaded_distance_raw'], loaded_distance, delta=.002)
            self.assertAlmostEqual(metrics['total_empty_distance_raw'], empty_distance, delta=.002)
            self.assertAlmostEqual(metrics['vehicle_utilization'], busy_time / (makespan * meta['fleet_size']), delta=2e-6)
            self.assertAlmostEqual(metrics['equipment_utilization'], process_time / (makespan * len(self.data['slots'])), delta=2e-6)
            # Region time partitions into resource waiting, travel, loading and
            # unloading, effective machine service; no unaccounted delay.
            components = (waits + machine_wait + process_time + (loaded_distance + empty_distance) / meta['speed_raw_per_min']
                          + nr * (meta['load_min'] + meta['unload_min']))
            self.assertAlmostEqual(sum(cycles), components, delta=.01)

    def test_analytical_two_task_queue(self):
        manifest = [dict(task_id=f'T{i}', part='test', step=1, group='G', release=0,
                         source='S', target='T', nominal_process_min=2, process_min=2)
                    for i in (1, 2)]
        assignments = {'T1': 'M', 'T2': 'M'}
        config = dict(fleet_size=1, initial_equipment=['S'], speed_raw_per_min=1,
                      load_min=0, unload_min=0, horizon_min=5)
        router = TinyRouter()
        case = self.engine.simulate_case(manifest, assignments, router, config)
        finishes = [max(s['t1'] for s in t['timeline']) for t in case['tasks']]
        self.assertEqual(finishes, [4, 7])
        metric = case['metrics']
        self.assertAlmostEqual(metric['total_loaded_distance_raw'], 4)
        self.assertAlmostEqual(metric['total_empty_distance_raw'], 2)
        self.assertAlmostEqual(metric['mean_region_time_min'], 5.5)
        self.assertAlmostEqual(metric['mean_transport_request_min'], 1.75)
        self.assertAlmostEqual(metric['vehicle_utilization'], 6 / 7)
        self.assertEqual(metric['completed_by_horizon'], 1)
        self.assertEqual(metric['unfinished_by_horizon'], 1)

    def test_analytical_machine_wait(self):
        # Transportation finishes at t=1 and t=3. A ten-minute machine service
        # starts at 1 then 11, so the second task must wait exactly 8 minutes.
        manifest = [dict(task_id=f'T{i}', part='test', step=1, group='G', release=0,
                         source='S', target='T', nominal_process_min=10, process_min=10)
                    for i in (1, 2)]
        case = self.engine.simulate_case(
            manifest, {'T1': 'M', 'T2': 'M'}, TinyRouter(),
            dict(fleet_size=1, initial_equipment=['S'], speed_raw_per_min=1,
                 load_min=0, unload_min=0, horizon_min=15))
        finishes = [max(s['t1'] for s in t['timeline']) for t in case['tasks']]
        self.assertEqual(finishes, [12, 23])
        self.assertAlmostEqual(case['metrics']['mean_wait_machine_min'], 4)
        self.assertAlmostEqual(case['metrics']['mean_region_time_min'], 17.5)


if __name__ == '__main__':
    unittest.main()
