"""Build the offline simulation viewer and link it from the Week 6 explainer."""
from pathlib import Path
from collections import defaultdict
import csv
import json
import math

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = ROOT / 'week7/simulation/results.json'
OUTPUT = ROOT / 'week7/历史版本/A2_A3局部回放.html'


def build_factory_context(root=ROOT):
    """Display-only geometry; does not add jobs/resources to the DES model.

    Bay outlines are envelopes of equipment and assigned rail endpoints under
    the inherited center-anchor convention, not authoritative physical bounds.
    """
    raw = root / 'analysis/smat_layout_viz/tables/raw'
    with (raw / 'Equipment.csv').open(encoding='utf-8-sig', newline='') as file:
        records = list(csv.DictReader(file))
    with (raw / 'Bay.csv').open(encoding='utf-8-sig', newline='') as file:
        bay_records = list(csv.DictReader(file))
    with (raw / 'Address.csv').open(encoding='utf-8-sig', newline='') as file:
        addresses = {r['NAME']: (float(r['POSITION_X'])/1000,
                                 float(r['POSITION_Y'])/1000) for r in csv.DictReader(file)}
    with (raw / 'Rail.csv').open(encoding='utf-8-sig', newline='') as file:
        rail_records = list(csv.DictReader(file))
    rail_points = defaultdict(list)
    for rail in rail_records:
        rail_points[rail['BAY_NAME']].extend([addresses[rail['FROM_NODE']], addresses[rail['TO_NODE']]])
    fixed_groups = {'STOCKER', 'COMMIT', 'COMPLETE'}
    equipment, by_bay = [], defaultdict(list)
    for row in records:
        item = {'name': row['NAME'], 'group': row['TOOL_GROUP'], 'bay': row['BAY'],
                'x': round(float(row['POSITION_X']) / 1000, 6),
                'y': round(float(row['POSITION_Y']) / 1000, 6),
                'width': round(float(row['WIDTH']) / 1000, 6),
                'height': round(float(row['HEIGHT']) / 1000, 6),
                'kind': 'fixed_amhs' if row['TOOL_GROUP'] in fixed_groups else 'production'}
        assert all(math.isfinite(item[k]) for k in ('x', 'y', 'width', 'height'))
        assert item['width'] > 0 and item['height'] > 0
        equipment.append(item)
        by_bay[item['bay']].append(item)
    bays = []
    for row in bay_records:
        members = by_bay.get(row['NAME'], [])
        corners = [(e['x']-e['width']/2, e['y']-e['height']/2) for e in members]
        corners.extend((e['x']+e['width']/2, e['y']+e['height']/2) for e in members)
        corners.extend(rail_points[row['NAME']])
        if not corners:
            continue
        bounds = {'x0': min(p[0] for p in corners) - 1,
                  'x1': max(p[0] for p in corners) + 1,
                  'y0': min(p[1] for p in corners) - 1,
                  'y1': max(p[1] for p in corners) + 1}
        bays.append({'name': row['NAME'], **{k: round(v, 6) for k, v in bounds.items()},
                     'count': len(members), 'simulated': row['NAME'] in {'A2', 'A3'}})
    assert len({e['name'] for e in equipment}) == len(equipment)
    assert not set(by_bay).difference(b['NAME'] for b in bay_records)
    fixed_count = sum(e['kind'] == 'fixed_amhs' for e in equipment)
    return {'equipment': equipment, 'bays': bays,
            'counts': {'equipment': len(equipment), 'production': len(equipment)-fixed_count,
                       'fixed_amhs': fixed_count, 'bays': len(bay_records)},
            'boundary_note': 'Bay 外框由设备矩形与所属轨道端点联合包络推导，仅作区域定位示意，不是原始物理边界；设备按中心锚点假设绘制。',
            'simulation_note': '只有 A2/A3 的任务、车辆及加工排队参与动态仿真，其余设备为静态布局背景。',
            'source_files': ['analysis/smat_layout_viz/tables/raw/Equipment.csv',
                             'analysis/smat_layout_viz/tables/raw/Bay.csv',
                             'analysis/smat_layout_viz/tables/raw/Address.csv',
                             'analysis/smat_layout_viz/tables/raw/Rail.csv']}


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    data['factory'] = build_factory_context()
    for scenario in data['scenarios']:
        assert set(scenario['cases']) == {'before', 'after'}
        # Keep the audit event/request log in results.json. The viewer derives
        # the selected-task event list and elapsed values from its timeline.
        for case in scenario['cases'].values():
            case.pop('events', None)
            case.pop('requests', None)
            for task in case['tasks']:
                task.pop('metrics', None)
    html = (HERE / 'index.template.html').read_text(encoding='utf-8')
    html = html.replace('__PLAYER_CSS__', (HERE / 'player.css').read_text(encoding='utf-8'))
    html = html.replace('__SIM_DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    html = html.replace('__PLAYER_JS__', (HERE / 'player.js').read_text(encoding='utf-8'))
    assert '__SIM_DATA__' not in html
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    html = html.replace('../week6/汇报成稿/MILP交互展示.html', '../../week6/汇报成稿/MILP交互展示.html')
    OUTPUT.write_text(html, encoding='utf-8')
    banner = '<p id="week7-simulation-link"><a href="../../week7/全厂制造仿真.html">本周动态仿真：全厂物流与加工 →</a></p>'
    for path in [ROOT / 'week6/交互展示/index.template.html',
                 ROOT / 'week6/汇报成稿/MILP交互展示.html']:
        source = path.read_bytes().decode('utf-8')
        if 'id="week7-simulation-link"' not in source:
            anchor = '  <nav class="tabs"'
            assert anchor in source, path
            newline = '\r\n' if '\r\n' in source else '\n'
            source = source.replace(anchor, '  ' + banner + newline + anchor, 1)
            path.write_bytes(source.encode('utf-8'))
    print(json.dumps({'viewer': str(OUTPUT.relative_to(ROOT)),
                      'bytes': OUTPUT.stat().st_size, 'scenarios': len(data['scenarios'])},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
