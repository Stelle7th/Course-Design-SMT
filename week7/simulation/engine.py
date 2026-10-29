"""Reproducible two-Bay logistics and processing DES (Python standard library).

The simulation consumes saved week6 allocations. It does not solve a new MILP.
Time is in minutes; distances retain the source data's coordinate units.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
import copy
import csv
import hashlib
import heapq
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_FILE = Path(__file__).resolve().parent / 'results.json'


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def percentile95(values):
    return sorted(values)[max(0, math.ceil(len(values) * .95) - 1)] if values else 0.


class Router:
    """Directed rail shortest paths with representative-port offsets.

    Uses the same Manhattan edge lengths and clamped representative ports as E1.
    Reuses the saved Week 6 node sequence whenever a planned path exists. Equal
    shortest distances do not imply the same predecessor chain, so independently
    rerunning Dijkstra is reserved for previously unplanned empty-vehicle paths.
    Polyline drawing follows source node coordinates, including diagonal chords.
    """
    def __init__(self, root=ROOT):
        raw = root / 'analysis/smat_layout_viz/tables/raw'
        addresses = read_csv(raw / 'Address.csv')
        self.nodes = [[float(r['POSITION_X']), float(r['POSITION_Y'])] for r in addresses]
        self.node_index = {r['NAME']: i for i, r in enumerate(addresses)}
        self.rails = {}
        self.graph = [[] for _ in addresses]
        for r in read_csv(raw / 'Rail.csv'):
            a, b = self.node_index[r['FROM_NODE']], self.node_index[r['TO_NODE']]
            pa, pb = self.nodes[a], self.nodes[b]
            length = abs(pa[0]-pb[0]) + abs(pa[1]-pb[1])
            assert length > 0, r['NAME']
            self.rails[r['NAME']] = {'a': a, 'b': b, 'length': length}
            self.graph[a].append((b, length))
        self.ports = {}
        for r in read_csv(root / 'week6/output/e1_reference_lp_full/selected_equipment_ports.csv'):
            rail = self.rails[r['rail_name']]
            offset = min(rail['length'], max(0., float(r['port_distance_clamped'])))
            a, b = self.nodes[rail['a']], self.nodes[rail['b']]
            fraction = offset / rail['length']
            point = [a[i] + (b[i]-a[i])*fraction for i in (0, 1)]
            self.ports[r['equipment_name']] = {'rail_name': r['rail_name'], 'offset': offset, 'point': point}
        self.trees = {}
        self.paths = {}
        planning = json.loads((root / 'week6/交互展示/milp-data.json').read_text(encoding='utf-8'))
        self.planned_paths = planning['network']['paths']
        # Saved node indices must still refer to the same source network. The
        # Week 6 display coordinates were rounded to five decimal places.
        assert len(planning['network']['nodes']) == len(self.nodes)
        for previous, current in zip(planning['network']['nodes'], self.nodes):
            assert max(abs(a-b/1000) for a, b in zip(previous, current)) <= .0000051

    def shortest_tree(self, source):
        if source in self.trees:
            return self.trees[source]
        distances = [math.inf] * len(self.nodes)
        previous = [-1] * len(self.nodes)
        distances[source] = 0.
        queue = [(0., source)]
        while queue:
            distance, u = heapq.heappop(queue)
            if distance != distances[u]:
                continue
            for v, length in self.graph[u]:
                candidate = distance + length
                if candidate < distances[v] - 1e-9:
                    distances[v], previous[v] = candidate, u
                    heapq.heappush(queue, (candidate, v))
        self.trees[source] = distances, previous
        return distances, previous

    def route(self, source, target):
        key = source + '>' + target
        if key in self.paths:
            return key
        sp, tp = self.ports[source], self.ports[target]
        sr, tr = self.rails[sp['rail_name']], self.rails[tp['rail_name']]
        distances, previous = self.shortest_tree(sr['b'])
        via = sr['length'] - sp['offset'] + distances[tr['a']] + tp['offset']
        direct = (tp['offset']-sp['offset'] if sp['rail_name'] == tp['rail_name']
                  and tp['offset'] >= sp['offset'] else math.inf)
        if direct <= via + 1e-9:
            length = direct
            sequence = []
            points = [sp['point'], tp['point']]
        else:
            length = via
            assert math.isfinite(length), (source, target)
            sequence, cursor = [tr['a']], tr['a']
            while cursor != sr['b']:
                cursor = previous[cursor]
                assert cursor >= 0, (source, target)
                sequence.append(cursor)
            sequence.reverse()
            points = [sp['point']] + [self.nodes[n] for n in sequence] + [tp['point']]
        geometry_source = 'directed_shortest_path'
        if key in self.planned_paths:
            # Preserve the plan's exact topology. A new heapq predecessor tree
            # can choose a different, equally short parallel corridor from the
            # SciPy predecessor tree used by the original planning page.
            planned = self.planned_paths[key]
            sequence = list(planned['nodes'])
            if sequence:
                assert sequence[0] == sr['b'] and sequence[-1] == tr['a'], key
                graph_length = 0.
                for a, b in zip(sequence, sequence[1:]):
                    matching = [cost for node, cost in self.graph[a] if node == b]
                    assert matching, (key, a, b)
                    graph_length += min(matching)
                saved_length = sr['length'] - sp['offset'] + graph_length + tp['offset']
            else:
                saved_length = direct
            assert abs(saved_length-length) < 1e-4, (key, saved_length, length)
            points = [sp['point']] + [self.nodes[n] for n in sequence] + [tp['point']]
            geometry_source = 'saved_week6_plan'
        reduced = []
        for point in points:
            point = [round(v/1000, 6) for v in point]
            if not reduced or point != reduced[-1]:
                reduced.append(point)
        self.paths[key] = {'points': reduced, 'distance_raw': round(length, 6),
                           'node_ids': sequence, 'geometry_source': geometry_source}
        return key

    def geometry(self):
        return {'nodes': [[round(v/1000, 6) for v in p] for p in self.nodes],
                'rails': [[r['a'], r['b']] for r in self.rails.values()],
                'paths': self.paths}


def apportion(weights, count):
    """Largest remainder, stable ties; integer total is exactly count."""
    weights = dict(sorted(weights.items()))
    total = sum(weights.values())
    assert total > 0 and count >= 0
    quotas = {key: value/total*count for key, value in weights.items()}
    counts = {key: math.floor(value) for key, value in quotas.items()}
    remaining = count - sum(counts.values())
    for key in sorted(quotas, key=lambda k: (-(quotas[k]-counts[k]), k))[:remaining]:
        counts[key] += 1
    return counts


def make_workload(data, release_window=10080., seed=20261029):
    """Identical source/target/task IDs for both allocations, synthetic arrivals.

    Excludes the three operations with multiple external endpoints. Their saved
    aggregate marginals do not identify the same source-target pairing per lot.
    """
    selected, excluded = [], []
    for op in sorted(data['operations'], key=lambda o: (int(o['part'].split('_')[-1]), o['step'])):
        endpoints = []
        for case in ('before', 'after'):
            endpoints.append(tuple(tuple(sorted({r['external_equipment'] for r in op[case]
                                                  if r['direction'] == direction}))
                                   for direction in ('in', 'out')))
        if endpoints[0] != endpoints[1] or any(len(v) != 1 for pair in endpoints for v in pair):
            excluded.append(op['key'])
        else:
            selected.append(op)
    rng = random.Random(seed)
    manifest, assignments = [], {'before': {}, 'after': {}}
    for op in selected:
        count = int(math.floor(op['demand']+.5))
        assert count > 0
        source = next(r['external_equipment'] for r in op['before'] if r['direction'] == 'in')
        target = next(r['external_equipment'] for r in op['before'] if r['direction'] == 'out')
        phase = rng.random()
        # A stratified deterministic schedule: count tasks across the full window.
        # Same phases and order are used in every layout and scenario.
        tasks = []
        for i in range(count):
            tid = f"{op['part']}-s{op['step']}-L{i+1:02}"
            task = {'task_id': tid, 'part': op['part'], 'step': op['step'],
                    'group': op['group'], 'source': source, 'target': target,
                    'release': (i+phase)/count*release_window,
                    'process_min': op['tau']/.85, 'nominal_process_min': op['tau']}
            tasks.append(task)
        manifest.extend(tasks)
        for case in ('before', 'after'):
            weight = defaultdict(float)
            for row in op[case]:
                if row['direction'] == 'in':
                    weight[row['slot']] += row['flow_lots']
            counts = apportion(weight, count)
            # Spread slot quotas evenly through the task sequence, rather than
            # assigning all work for one machine at the start of the horizon.
            emitted = defaultdict(int)
            for i, task in enumerate(tasks):
                allowed = [slot for slot in counts if emitted[slot] < counts[slot]]
                slot = max(allowed, key=lambda s: ((i+1)*counts[s]/count-emitted[s], s))
                assignments[case][task['task_id']] = slot
                emitted[slot] += 1
    return sorted(manifest, key=lambda t: (t['release'], t['task_id'])), assignments, selected, excluded


def simulate_case(manifest, assignments, router, config):
    """FCFS global transport queue and FCFS capacity-one machine queues.

    router.route(source, target) returns a key; router.paths[key] contains
    distance_raw and points. This small interface also supports hand-checkable
    tiny-network unit tests without the course dataset.
    """
    tasks = {t['task_id']: {**copy.deepcopy(t), 'slot': assignments[t['task_id']],
                           'equipment': assignments[t['task_id']], 'timeline': [],
                           'metrics': {}} for t in manifest}
    initial = config['initial_equipment']
    assert len(initial) == config['fleet_size']
    vehicles = [{'vehicle_id': f'OHT-{i+1:02}', 'initial_equipment': p,
                 'position': p, 'idle': True, 'legs': [], 'busy_intervals': []}
                for i, p in enumerate(initial)]
    events, requests, scheduled = [], [], []
    pending = deque()
    machine_queues, machine_busy = defaultdict(deque), {}
    sequence = 0

    def schedule(time, kind, payload):
        nonlocal sequence
        sequence += 1
        heapq.heappush(scheduled, (time, sequence, kind, payload))

    def record(time, task, kind, **extra):
        events.append({'time': time, 'task_id': task['task_id'], 'type': kind, **extra})

    def segment(task, state, t0, t1, **extra):
        assert t1 >= t0 - 1e-9
        task['timeline'].append({'state': state, 't0': t0, 't1': t1, **extra})

    def enqueue_transport(time, task, phase):
        request = {'request_id': task['task_id']+'-'+phase, 'task_id': task['task_id'],
                   'phase': phase, 'created_at': time,
                   'source': task['source'] if phase == 'in' else task['slot'],
                   'target': task['slot'] if phase == 'in' else task['target']}
        requests.append(request)
        pending.append(request)

    def dispatch(time):
        # Oldest request first; lowest numbered idle vehicle, independent of
        # layout. Deliberately avoids adding a second layout-specific optimizer.
        idle = [v for v in vehicles if v['idle']]
        while pending and idle:
            request = pending.popleft()
            vehicle = idle.pop(0)
            task, phase = tasks[request['task_id']], request['phase']
            vehicle['idle'] = False
            empty_path = router.route(vehicle['position'], request['source'])
            loaded_path = router.route(request['source'], request['target'])
            empty_distance = router.paths[empty_path]['distance_raw']
            loaded_distance = router.paths[loaded_path]['distance_raw']
            empty_time = empty_distance/config['speed_raw_per_min']
            loaded_time = loaded_distance/config['speed_raw_per_min']
            arrival = time+empty_time
            depart = arrival+config['load_min']
            destination = depart+loaded_time
            delivered = destination+config['unload_min']
            vid = vehicle['vehicle_id']
            request.update({'assigned_at': time, 'pickup_at': arrival, 'delivered_at': delivered,
                            'vehicle_id': vid, 'path': loaded_path, 'empty_path': empty_path})
            segment(task, 'wait_vehicle_'+phase, request['created_at'], time)
            segment(task, 'empty_'+phase, time, arrival, vehicle_id=vid, path=empty_path)
            segment(task, 'load_'+phase, arrival, depart, vehicle_id=vid)
            segment(task, 'loaded_'+phase, depart, destination, vehicle_id=vid, path=loaded_path)
            segment(task, 'unload_'+phase, destination, delivered, vehicle_id=vid)
            vehicle['legs'].append({'task_id': task['task_id'], 'phase': phase, 'loaded': False,
                                    't0': time, 't1': arrival, 'path': empty_path,
                                    'distance_raw': empty_distance})
            vehicle['legs'].append({'task_id': task['task_id'], 'phase': phase, 'loaded': True,
                                    't0': depart, 't1': destination, 'path': loaded_path,
                                    'distance_raw': loaded_distance})
            vehicle['busy_intervals'].append({'t0': time, 't1': delivered, 'task_id': task['task_id']})
            vehicle['position'] = request['target']
            schedule(delivered, 'delivery', (request, vehicle))

    def start_machine(time, slot):
        if machine_busy.get(slot) or not machine_queues[slot]:
            return
        arrival, tid = machine_queues[slot].popleft()
        task = tasks[tid]
        machine_busy[slot] = True
        segment(task, 'wait_equipment', arrival, time)
        end = time+task['process_min']
        segment(task, 'processing', time, end)
        record(time, task, 'processing_start', equipment=slot)
        schedule(end, 'processing_done', task)

    for task in tasks.values():
        schedule(task['release'], 'release', task)
    while scheduled:
        time, _, kind, payload = heapq.heappop(scheduled)
        if kind == 'release':
            record(time, payload, 'released')
            enqueue_transport(time, payload, 'in')
        elif kind == 'delivery':
            request, vehicle = payload
            vehicle['idle'] = True
            task = tasks[request['task_id']]
            if request['phase'] == 'in':
                machine_queues[task['slot']].append((time, task['task_id']))
                start_machine(time, task['slot'])
            else:
                task['completed_at'] = time
                record(time, task, 'completed')
        elif kind == 'processing_done':
            task = payload
            machine_busy[task['slot']] = False
            record(time, task, 'processing_done', equipment=task['slot'])
            enqueue_transport(time, task, 'out')
            start_machine(time, task['slot'])
        dispatch(time)

    assert all('completed_at' in t for t in tasks.values())
    assert not pending and all(v['idle'] for v in vehicles)
    makespan = max((t['completed_at'] for t in tasks.values()), default=0.)
    for task in tasks.values():
        prefix = lambda name: sum(s['t1']-s['t0'] for s in task['timeline'] if s['state'].startswith(name))
        task['metrics'] = {
            'wait_vehicle_min': prefix('wait_vehicle'), 'wait_equipment_min': prefix('wait_equipment'),
            'loaded_transport_min': prefix('loaded_'), 'empty_transport_min': prefix('empty_'),
            'load_unload_min': prefix('load_')+prefix('unload_'), 'process_min': task['process_min'],
            'sojourn_min': task['completed_at']-task['release'],
            'loaded_distance_raw': sum(router.paths[s['path']]['distance_raw'] for s in task['timeline'] if s['state'].startswith('loaded_')),
            'empty_distance_raw': sum(router.paths[s['path']]['distance_raw'] for s in task['timeline'] if s['state'].startswith('empty_'))}
    count = len(tasks)
    means = lambda key: sum(t['metrics'][key] for t in tasks.values())/count if count else 0.
    request_times = [r['delivered_at']-r['created_at'] for r in requests]
    completed_by_horizon = sum(t['completed_at'] <= config['horizon_min']+1e-9 for t in tasks.values())
    busy = sum(b['t1']-b['t0'] for v in vehicles for b in v['busy_intervals'])
    total_loaded = sum(t['metrics']['loaded_distance_raw'] for t in tasks.values())
    total_empty = sum(t['metrics']['empty_distance_raw'] for t in tasks.values())
    metrics = {'task_count': count, 'completed': count, 'completed_by_horizon': completed_by_horizon,
               'wip_at_horizon': count-completed_by_horizon, 'unfinished_by_horizon': count-completed_by_horizon,
               'makespan_min': makespan, 'mean_wait_vehicle_min': means('wait_vehicle_min'),
               'mean_wait_equipment_min': means('wait_equipment_min'), 'mean_wait_machine_min': means('wait_equipment_min'),
               'mean_transport_min': sum(request_times)/len(request_times) if request_times else 0.,
               'mean_transport_request_min': sum(request_times)/len(request_times) if request_times else 0.,
               'p95_transport_min': percentile95(request_times), 'p95_transport_request_min': percentile95(request_times),
               'mean_loaded_transport_min': means('loaded_transport_min'),
               'mean_empty_transport_min': means('empty_transport_min'),
               'mean_sojourn_min': means('sojourn_min'), 'mean_region_time_min': means('sojourn_min'),
               'loaded_distance_raw': total_loaded, 'total_loaded_distance_raw': total_loaded,
               'empty_distance_raw': total_empty, 'total_empty_distance_raw': total_empty,
               'vehicle_utilization': busy/(makespan*len(vehicles)) if makespan and vehicles else 0.,
               'equipment_utilization': sum(t['process_min'] for t in tasks.values())/(makespan*config.get('equipment_count', len(set(assignments.values())))) if makespan else 0.}
    for v in vehicles:
        v.pop('idle'); v.pop('position')
    return {'tasks': list(tasks.values()), 'vehicles': vehicles, 'requests': requests,
            'events': sorted(events, key=lambda e: (e['time'], e['task_id'], e['type'])), 'metrics': metrics}


def rounded(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [rounded(v) for v in value]
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    return value


def summarize_results(output):
    """Small audit-friendly summary and descriptive queue attribution."""
    rows, attribution = [], {}
    for scenario in output['scenarios']:
        groups = {}
        for label, case in scenario['cases'].items():
            rows.append({'scenario': scenario['id'], 'layout': label, **case['metrics']})
            per_group = defaultdict(lambda: {'tasks': 0, 'waiting_min': 0., 'processing_min': 0., 'slots': set()})
            per_slot = defaultdict(lambda: {'tasks': 0, 'waiting_min': 0., 'processing_min': 0.})
            for task in case['tasks']:
                wait = task['metrics']['wait_equipment_min']
                for values in (per_group[task['group']], per_slot[task['slot']]):
                    values['tasks'] += 1
                    values['waiting_min'] += wait
                    values['processing_min'] += task['process_min']
                per_group[task['group']]['slots'].add(task['slot'])
            groups[label] = {'groups': {g: {**v, 'slots': sorted(v['slots']),
                                          'mean_wait_min': v['waiting_min']/v['tasks']}
                                       for g, v in per_group.items()}, 'slots': dict(per_slot)}
        group_changes = []
        for group in sorted(set(groups['before']['groups']) | set(groups['after']['groups'])):
            before, after = groups['before']['groups'][group], groups['after']['groups'][group]
            group_changes.append({'group': group, 'tasks': before['tasks'],
                                  'before_wait_sum_min': before['waiting_min'],
                                  'after_wait_sum_min': after['waiting_min'],
                                  'queue_increase_min': after['waiting_min']-before['waiting_min'],
                                  'before_mean_wait_min': before['mean_wait_min'],
                                  'after_mean_wait_min': after['mean_wait_min'],
                                  'before_active_slots': before['slots'],
                                  'after_active_slots': after['slots']})
        slot_changes = []
        for slot in sorted(set(groups['before']['slots']) | set(groups['after']['slots'])):
            b = groups['before']['slots'].get(slot, {'tasks': 0, 'waiting_min': 0.})
            a = groups['after']['slots'].get(slot, {'tasks': 0, 'waiting_min': 0.})
            slot_changes.append({'slot': slot, 'before_tasks': b['tasks'], 'after_tasks': a['tasks'],
                                 'before_wait_sum_min': b['waiting_min'],
                                 'after_wait_sum_min': a['waiting_min'],
                                 'queue_increase_min': a['waiting_min']-b['waiting_min']})
        attribution[scenario['id']] = {'groups': group_changes,
                                      'slots': sorted(slot_changes, key=lambda r: -r['queue_increase_min'])}
    return rounded({'metrics': rows, 'queue_attribution': attribution,
                    'interpretation': '描述性分解：比较相同任务及到达规则下不同加工槽位分配的等待总量，不把队列变化全部归因于单台设备搬迁。MILP目标未惩罚排队或保证负荷均衡。'})


def build_results(root=ROOT):
    data_file = root / 'week6/交互展示/milp-data.json'
    data = json.loads(data_file.read_text(encoding='utf-8'))
    router = Router(root)
    manifest, assignments, selected, excluded = make_workload(data)
    slots = {s['slot_name']: s for s in data['slots']}
    common = {'fleet_size': 4, 'initial_equipment': ['LITH0213']*4,
              'speed_raw_per_min': 90000., 'load_min': .5, 'unload_min': .5,
              'horizon_min': 10080., 'equipment_count': 48, 'effective_availability': .85}
    scenarios = []
    for sid, label, window, description in [
            ('regular', '常规：7 天均匀到达', 10080., '560 次区域工序访问，按每工序分层均匀释放到 7 天；是统一构造的到达情景，不是实测轨迹。'),
            ('burst', '压力：60 分钟集中到达', 60., '相同的 560 个任务压缩至 60 分钟释放，演示有限车辆与设备竞争；不是原需求系数下的实际到达记录。')]:
        tasks = copy.deepcopy(manifest)
        for task in tasks:
            task['release'] *= window/10080.
        cases = {}
        for case in ('before', 'after'):
            result = simulate_case(tasks, assignments[case], router, common)
            for task in result['tasks']:
                slot = slots[task['slot']]
                assert slot['original_group' if case == 'before' else 'optimized_group'] == task['group']
                task['equipment'] = slot['old_equipment' if case == 'before' else 'new_equipment']
            cases[case] = result
        scenarios.append({'id': sid, 'label': label, 'description': description,
                          'task_count': len(tasks), 'operation_count': len(selected),
                          'fleet_size': common['fleet_size'], 'horizon_min': common['horizon_min'],
                          'release_window_min': window, 'cases': cases})
    # Check graph distances against all existing saved boundary routes before
    # relying on it for previously uncomputed empty vehicle paths.
    max_distance_error = 0.
    for op in data['operations']:
        for case in ('before', 'after'):
            for row in op[case]:
                a, b = (row['external_equipment'], row['slot']) if row['direction'] == 'in' else (row['slot'], row['external_equipment'])
                key = router.route(a, b)
                max_distance_error = max(max_distance_error, abs(router.paths[key]['distance_raw']-row['distance_raw']))
    assert max_distance_error < 1e-4, max_distance_error
    return rounded({'meta': {
        'schema_version': 1, 'title': 'A2/A3 物流与加工排队离散事件仿真',
        'time_unit': 'min', 'distance_unit': '原始坐标单位', 'coordinate_scale': 1000,
        'speed_raw_per_min': common['speed_raw_per_min'], 'load_min': .5, 'unload_min': .5,
        'effective_availability': .85, 'fleet_size': 4, 'horizon_min': 10080.,
        'seed': 20261029, 'selected_operations': [o['key'] for o in selected],
        'excluded_operations': excluded,
        'selection': '从原 59 道区域工序中选择 56 道单一外部源、单一外部目标工序；排除 3 道拆分边界工序，避免连续流未给出逐 lot 源目标配对的歧义。',
        'workload': '每道工序需求按四舍五入得到 10 次区域访问，共 560 个共同整数任务；两布局 task_id、到达时刻、外部源与目标、加工时间完全相同。槽位按保存的加工量比例用最大余数法整数化。',
        'assumptions': [
            '这是合成区域工序访问任务，不是实际批次历史，也不是完整产品生产路线。A2/A3 原案例无正的区域内部连续工序流。',
            '4 辆局部实验车辆，共用相同的 LITH0213 初始端口；非从全厂 500 辆车中抽取，初始停车区容量不建模。',
            '全局搬运请求先到先服务；同刻选择编号最小的空闲车；设备队列先到先服务且每台容量为 1。',
            '声明情景假设：原始坐标单位按 mm 解释，匀速 1500 mm/s = 90000 原始单位/min；单位与轨道速度字段尚未校准，不称为现场真实分钟。',
            '每次装载、卸载各 0.5 min 为实验假设；忽略加减速、追车、轨道区段互斥、ZCU、防撞及死锁。队列仅来自车辆和设备容量。',
            '设备输入与输出缓存暂不限制容量；加工完成即释放设备，等待出站搬运不阻塞后续加工；装卸占用车辆但不另外锁定设备或端口。',
            '有效加工占用时间 = 保存的每 lot 名义加工机时 / 0.85，是有效可用性确定性折算，不是随机故障或真实停机日历。',
            '运输请求周转时间 = 等车 + 空车接货 + 装载 + 满载行驶 + 卸载；区域停留时间还包含设备等待、加工与出站请求。',
            '仿真推进到全部任务完成，另统计第 7 天完成数和未完工任务；车辆、设备利用率以全部任务完工时刻为分母。',
            '本周只仿真 56 道工序且使用整数任务及共同到达规则，距离改善率不强行等于上周 59 道连续流的 0.582%，时间收益需重新测量。'],
        'source_files': ['week6/交互展示/milp-data.json', 'week6/output/e1_reference_lp_full/selected_equipment_ports.csv', 'analysis/smat_layout_viz/tables/raw/Address.csv', 'analysis/smat_layout_viz/tables/raw/Rail.csv'],
        'source_sha256': hashlib.sha256(data_file.read_bytes()).hexdigest(),
        'max_saved_distance_error_raw': max_distance_error,
        'path_geometry_policy': '载货及其他已保存路径沿用上周规划的精确节点序列；仅未规划的空驶路径重新计算有向最短路。节点和端口坐标保留本周较高精度。',
        'metrics_scope': 'Full drain-to-completion metrics; horizon counts additionally use 10080 min.'},
        'slots': data['slots'], 'network': router.geometry(), 'scenarios': scenarios})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()
    output = build_results()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    summary = summarize_results(output)
    (args.output.parent / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    with (args.output.parent / 'metrics.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary['metrics'][0]))
        writer.writeheader()
        writer.writerows(summary['metrics'])
    print(json.dumps({'output': str(args.output), 'bytes': args.output.stat().st_size,
                      'task_count_per_case': output['scenarios'][0]['task_count'],
                      'paths': len(output['network']['paths']),
                      'scenarios': {s['id']: {c: v['metrics'] for c, v in s['cases'].items()} for s in output['scenarios']}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
