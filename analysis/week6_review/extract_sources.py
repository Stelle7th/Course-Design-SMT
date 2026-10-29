from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import json
import hashlib
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'source_text'
OUT.mkdir(parents=True, exist_ok=True)
sources = []
seen = set()
for p in ROOT.rglob('*'):
    if p.suffix.lower() not in {'.pdf', '.pptx'}:
        continue
    if '新建文件夹' in p.parts or 'week6_review' in p.parts or p.name.startswith('._') or '__MACOSX' in p.parts:
        continue
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if digest in seen:
        continue
    seen.add(digest)
    if p.suffix.lower() == '.pdf':
        reader = PdfReader(str(p))
        pages = [f'=== PAGE {i+1} ===\n{page.extract_text() or ""}' for i,page in enumerate(reader.pages)]
    else:
        with ZipFile(p) as z:
            names = sorted([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')],key=lambda n:int(n.split('slide')[-1].split('.')[0]))
            pages = []
            for i,n in enumerate(names):
                root = ET.fromstring(z.read(n))
                texts = [e.text or '' for e in root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t')]
                pages.append(f'=== SLIDE {i+1} ===\n'+'\n'.join(texts))
    target = OUT / (str(len(sources)).zfill(2)+'_'+p.stem+'.txt')
    target.write_text('\n\n'.join(pages),encoding='utf-8')
    sources.append({'source':str(p),'extracted':str(target),'pages':len(pages),'chars':sum(map(len,pages)),'sha256':digest})
(OUT/'manifest.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(sources,ensure_ascii=False,indent=2))
