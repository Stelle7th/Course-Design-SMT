"""Bundle a standalone, offline full-fab simulator into both current entry paths."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def build():
    data = (HERE / 'factory-data.json').read_text(encoding='utf-8')
    payload = json.loads(data)
    payload['categories'] = json.loads((HERE / 'categories.json').read_text(encoding='utf-8'))
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    source = (HERE / 'index.html').read_text(encoding='utf-8')
    source = source.replace('__CSS__', (HERE / 'style.css').read_text(encoding='utf-8'))
    source = source.replace('__DATA__', data.replace('</', '<\\/'))
    script = (HERE / 'app.js').read_text(encoding='utf-8')
    assert 'setupMap();refresh(true);' in script
    script = script.replace('setupMap();refresh(true);', (HERE / 'focus.js').read_text(encoding='utf-8') + '\nsetupMap();setupFocus();refresh(true);')
    source = source.replace('__JS__', script)
    assert not any(token in source for token in ('__CSS__', '__DATA__', '__JS__'))
    for name in ['全厂制造仿真.html', 'A2_A3仿真展示.html']:
        target = ROOT / 'week7' / name
        target.write_text(source, encoding='utf-8')
        print(name, target.stat().st_size)


if __name__ == '__main__':
    build()
