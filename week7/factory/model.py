"""Full-fab deterministic DES: source WIP, recipe precedence, 500 real OHT starts.

Coordinates /1000, assumed metres. Simulation minutes; route lengths use the
same directed Manhattan rail metric as E1. This is a baseline, not a new MILP.
"""
from collections import defaultdict, deque, Counter
from pathlib import Path
import csv
import heapq
import json
import math
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HORIZON = 720.0
SPEED = 90.0  # assumed 1500 mm/s -> 90 m/min
LOAD = .25
AVAILABILITY = .85


def read(path, delimiter=','):
    with path.open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file, delimiter=delimiter))


class Network:
    def __init__(self, raw):
        rows = read(raw / 'Address.csv')
        self.nodes = [[float(r['POSITION_X']) / 1000, float(r['POSITION_Y']) / 1000] for r in rows]
        index = {r['NAME']: i for i, r in enumerate(rows)}
        self.rails, self.rail_index, self.reverse = [], {}, [[] for _ in rows]
        for r in read(raw / 'Rail.csv'):
            a, b = index[r['FROM_NODE']], index[r['TO_NODE']]
            length = sum(abs(x-y) for x, y in zip(self.nodes[a], self.nodes[b]))
            assert length > 0
            self.rail_index[r['NAME']] = len(self.rails)
            self.rails.append([a, b, length, r['BAY_NAME']])
            self.reverse[b].append((a, length))
        self.spots, self.spot_index, self.trees = [], {}, {}
        self.paths, self.path_index = [], {}

    def spot(self, rail_name, offset, name):
        rail = self.rail_index[rail_name]
        a, b, length, _ = self.rails[rail]
        offset = max(0., min(length, offset / 1000))
        x, y = [u + (v-u)*offset/length for u, v in zip(self.nodes[a], self.nodes[b])]
        i = len(self.spots)
        self.spots.append([rail, offset, x, y, name])
        return i

    def tree(self, destination):
        if destination not in self.trees:
            dist, successor = [math.inf] * len(self.nodes), [-1] * len(self.nodes)
            dist[destination] = 0.
            heap = [(0., destination)]
            while heap:
                cost, v = heapq.heappop(heap)
                if cost != dist[v]:
                    continue
                for u, length in self.reverse[v]:
                    candidate = cost + length
                    if candidate < dist[u] - 1e-10:
                        dist[u], successor[u] = candidate, v
                        heapq.heappush(heap, (candidate, u))
            self.trees[destination] = dist, successor
        return self.trees[destination]

    def distance(self, source, target):
        s, t = self.spots[source], self.spots[target]
        sr, tr = self.rails[s[0]], self.rails[t[0]]
        direct = t[1] - s[1] if s[0] == t[0] and t[1] >= s[1] else math.inf
        via = sr[2] - s[1] + self.tree(tr[0])[0][sr[1]] + t[1]
        return min(direct, via)

    def route(self, source, target):
        key = (source, target)
        if key not in self.path_index:
            s, t = self.spots[source], self.spots[target]
            sr, tr = self.rails[s[0]], self.rails[t[0]]
            dist, successor = self.tree(tr[0])
            direct = t[1] - s[1] if s[0] == t[0] and t[1] >= s[1] else math.inf
            via = sr[2] - s[1] + dist[sr[1]] + t[1]
            nodes = []
            if via < direct - 1e-9:
                u = sr[1]
                nodes.append(u)
                while u != tr[0]:
                    u = successor[u]
                    assert u >= 0, key
                    nodes.append(u)
            length = min(direct, via)
            assert math.isfinite(length), key
            self.path_index[key] = len(self.paths)
            self.paths.append([source, target, nodes, length])
        return self.path_index[key]


def load_inputs(root=ROOT):
    raw = root / 'analysis/smat_layout_viz/tables/raw'
    network = Network(raw)
    mappings = {r['equipment_name']: r for r in read(root / 'output/e0_audit/equipment_mapping.csv')}
    selected = {r['equipment_name']: r for r in read(root / 'output/e1_reference_lp_full/selected_equipment_ports.csv')}
    ports = defaultdict(list)
    for p in read(raw / 'Port.csv'):
        ports[p['EQP_NAME']].append(p)
    equipment, groups, names = [], defaultdict(list), {}
    for r in read(raw / 'Equipment.csv'):
        name = r['NAME']
        if name in selected:
            p = selected[name]
            spot = network.spot(p['rail_name'], float(p['port_distance_clamped']), name)
        else:
            p = sorted(ports[name], key=lambda x: x['NAME'])[0]
            spot = network.spot(p['RAILLINE_NAME'], float(p['DISTANCE']), name)
        group = mappings[name]['mapped_smt_stn'] or r['TOOL_GROUP']
        e = dict(name=name, group=group, bay=r['BAY'], spot=spot,
                 x=float(r['POSITION_X'])/1000, y=float(r['POSITION_Y'])/1000,
                 w=float(r['WIDTH'])/1000, h=float(r['HEIGHT'])/1000,
                 production=mappings[name]['mapping_status'] == 'matched')
        names[name] = len(equipment)
        groups[group].append(len(equipment))
        equipment.append(e)
    coverage = {r['route_stnfam']: r['target_smt_stn'] for r in read(root / 'output/e0_audit/route_coverage.csv')}
    smt = root / 'data/SMT2020_LVHM'
    recipes = []
    for i in range(1, 11):
        route = []
        for r in read(smt / f'route_{i}.txt', '\t'):
            group = coverage[r['STNFAM']]
            duration = float(r['PTIME'])
            if r['PTPER'] == 'per_piece':
                duration *= 25
            elif r['PTPER'] == 'per_batch':
                duration *= 25 / ((float(r['BATCHMN'])+float(r['BATCHMX']))/2)
            if group:
                assert groups[group], (i, r['STEP'], group)
                duration /= AVAILABILITY
            route.append(dict(step=int(r['STEP']), name=r['DESC'], group=group or 'Delay',
                              duration=duration, unit=r['PTPER']))
        recipes.append(route)
    vehicles = []
    for r in sorted(read(raw / 'Vehicle.csv'), key=lambda r: int(r['NAME'].rsplit('_', 1)[1])):
        vehicles.append(dict(name=r['NAME'], initial=network.spot(r['RAILLINE_NAME'], float(r['DISTANCE']), r['NAME'])))
    lots = []
    for row in read(smt / 'WIP.txt', '\t'):
        product = int(row['PART'].split('_')[1])-1
        recipe = recipes[product]
        op = next(i for i, o in enumerate(recipe) if o['step'] == int(row['CURSTEP']))
        # Unknown WIP location: reconstruct at a deterministic eligible machine
        # of the previous productive operation, never invent an observed location.
        previous = next((r for r in reversed(recipe[:op]) if r['group'] != 'Delay'), None)
        candidates = groups[previous['group']] if previous else groups['COMMIT']
        origin = candidates[len(lots) % len(candidates)]
        lots.append(dict(name=row['LOT'], product=product, start=op, release=0., origin=origin, source='WIP', visits=[], delays=[]))
    for row in read(smt / 'order.txt', '\t'):
        if not row['LOT'].startswith('Lot_'):
            continue
        product = int(row['PART'].split('_')[1])-1
        interval = float(row['REPEAT']) / .25
        for k in range(math.ceil(HORIZON/interval)):
            lots.append(dict(name=f"New_{product+1}_{k+1}", product=product, start=0,
                             release=k*interval, origin=groups['COMMIT'][product%4], source='订单生成', visits=[], delays=[]))
    return network, equipment, groups, recipes, vehicles, lots


def simulate(network, equipment, groups, recipes, vehicles, lots, horizon=HORIZON):
    heap, sequence = [], 0
    visits, delays, events = [], [], []
    machine_queues = [deque() for _ in equipment]
    machine_busy = [False] * len(equipment)
    work = [0.] * len(equipment)
    idle = set(range(len(vehicles)))
    locations = [v['initial'] for v in vehicles]
    for v in vehicles:
        v['trips'] = []
    requests = deque()

    def schedule(t, kind, index):
        nonlocal sequence
        sequence += 1
        heapq.heappush(heap, (t, sequence, kind, index))

    def log(t, kind, lot, obj):
        events.append([t, kind, lot, obj])

    def advance(t, lot_id, op, source):
        lot = lots[lot_id]
        recipe = recipes[lot['product']]
        if op < len(recipe) and recipe[op]['group'] == 'Delay':
            i = len(delays)
            delays.append(dict(lot=lot_id, op=op, start=t, end=t+recipe[op]['duration'], source=source))
            lot['delays'].append(i)
            log(t, 'delay', lot_id, source)
            schedule(delays[i]['end'], 'delay_end', i)
            return
        candidates = groups[recipe[op]['group']] if op < len(recipe) else groups['COMPLETE']
        source_spot = equipment[source]['spot']
        target = min(candidates, key=lambda e: (work[e]+network.distance(source_spot, equipment[e]['spot'])/SPEED, e))
        duration = recipe[op]['duration'] if op < len(recipe) else 0.
        i = len(visits)
        visits.append(dict(lot=lot_id, op=op, source=source, target=target, request=t,
                           dispatch=None, pickup=None, depart=None, arrive=None, delivered=None,
                           start=None, end=None, vehicle=None, empty=None, loaded=None, duration=duration))
        lot['visits'].append(i)
        work[target] += duration
        requests.append(i)
        log(t, 'request', lot_id, target)
        dispatch(t)

    def dispatch(t):
        while requests and idle:
            i = requests.popleft()
            visit = visits[i]
            source = equipment[visit['source']]['spot']
            target = equipment[visit['target']]['spot']
            v = min(idle, key=lambda v: (network.distance(locations[v], source), v))
            idle.remove(v)
            empty, loaded = network.route(locations[v], source), network.route(source, target)
            pickup = t+network.paths[empty][3]/SPEED
            depart = pickup+LOAD
            arrive = depart+network.paths[loaded][3]/SPEED
            delivered = arrive+LOAD
            visit.update(dispatch=t, pickup=pickup, depart=depart, arrive=arrive, delivered=delivered,
                         vehicle=v, empty=empty, loaded=loaded)
            vehicles[v]['trips'].append(i)
            log(t, 'dispatch', visit['lot'], v)
            schedule(delivered, 'delivered', i)

    def start_machine(t, e):
        if not machine_busy[e] and machine_queues[e]:
            i = machine_queues[e].popleft()
            visit = visits[i]
            machine_busy[e] = True
            visit.update(start=t, end=t+visit['duration'])
            log(t, 'process', visit['lot'], e)
            schedule(visit['end'], 'processed', i)

    for i, lot in enumerate(lots):
        schedule(lot['release'], 'release', i)
    while heap:
        t, _, kind, i = heapq.heappop(heap)
        if t > horizon:
            break
        if kind == 'release':
            advance(t, i, lots[i]['start'], lots[i]['origin'])
        elif kind == 'delay_end':
            d = delays[i]
            advance(t, d['lot'], d['op']+1, d['source'])
        elif kind == 'delivered':
            visit = visits[i]
            e, v = visit['target'], visit['vehicle']
            locations[v] = equipment[e]['spot']
            idle.add(v)
            log(t, 'delivered', visit['lot'], e)
            if visit['op'] >= len(recipes[lots[visit['lot']]['product']]):
                visit.update(start=t, end=t)
                lots[visit['lot']]['completed'] = t
                log(t, 'complete', visit['lot'], e)
            else:
                machine_queues[e].append(i)
                start_machine(t, e)
            dispatch(t)
        elif kind == 'processed':
            visit = visits[i]
            e = visit['target']
            machine_busy[e] = False
            work[e] = max(0., work[e]-visit['duration'])
            log(t, 'processed', visit['lot'], e)
            start_machine(t, e)
            advance(t, visit['lot'], visit['op']+1, e)
    events.sort(key=lambda e: e[0])
    metrics = {
        'lots': len(lots), 'initial_wip': sum(l['source']=='WIP' for l in lots),
        'completed_lots': sum('completed' in l for l in lots),
        'requests': len(visits), 'delivered': sum(v['delivered'] is not None and v['delivered'] <= horizon for v in visits),
        'processed': sum(v['end'] is not None and v['end'] <= horizon and v['duration'] > 0 for v in visits),
        'loaded_distance': sum(network.paths[v['loaded']][3] for v in visits if v['loaded'] is not None),
        'equipment_used': len({v['target'] for v in visits if v['start'] is not None and v['duration'] > 0}),
        'vehicles_used': sum(bool(v['trips']) for v in vehicles),
        'bays_used': sorted({equipment[v['target']]['bay'] for v in visits if v['duration'] > 0}),
    }
    return dict(visits=visits, delays=delays, events=events, metrics=metrics)


def build():
    start = time.monotonic()
    network, equipment, groups, recipes, vehicles, lots = load_inputs()
    result = simulate(network, equipment, groups, recipes, vehicles, lots)
    result.update(equipment=equipment, recipes=recipes, vehicles=vehicles, lots=lots,
                  nodes=network.nodes, rails=network.rails, spots=network.spots, paths=network.paths,
                  config=dict(horizon=HORIZON, speed=SPEED, load=LOAD, availability=AVAILABILITY,
                              vehicles=len(vehicles), seed='stable-source-order', layout='参考布局', version=2))
    (HERE / 'factory-data.json').write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    print(json.dumps(dict(**result['metrics'], paths=len(network.paths), build_seconds=round(time.monotonic()-start, 2)), ensure_ascii=False))


if __name__ == '__main__':
    build()
