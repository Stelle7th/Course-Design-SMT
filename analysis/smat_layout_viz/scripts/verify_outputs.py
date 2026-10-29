"""Independent output reconciliation with an alternate XLSX reader.
Read-only on source inputs. Run after build_layout.py and browser/visual QA.
"""
from pathlib import Path
import json, re, hashlib
import pandas as pd
import numpy as np
import openpyxl
from PIL import Image, ImageOps, ImageDraw

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]
SRC=ROOT/'analysis/a2_audit/smat2022'
checks=[]
def check(name,condition):
    checks.append({'check':name,'passed':bool(condition)})
    if not condition:raise AssertionError(name)
book=openpyxl.load_workbook(SRC/'SMAT_2022_Model_Data_-_LVHM_E.xlsx',read_only=True,data_only=False)
tables={}
for sheet in book:
    rows=[list(r) for r in sheet.iter_rows(values_only=True) if any(x is not None for x in r)]
    d=pd.DataFrame(rows[1:],columns=rows[0]);tables[sheet.title]=d
    exported=pd.read_csv(OUT/'tables/raw'/f'{sheet.title}.csv',keep_default_na=False)
    check(sheet.title+' independent row count',len(d)==len(exported))
    check(sheet.title+' independent NAME sequence',d.NAME.tolist()==exported.NAME.tolist())
book.close()
source=tables['Equipment'].copy()
production=source[~source.TOOL_GROUP.isin(['STOCKER','COMMIT','COMPLETE'])].copy()
production['STNFAM']=production.TOOL_GROUP.replace({'DefMet_FE_118':'DefMEt_FE_118'})
matrix=pd.read_csv(OUT/'tables/workcenter_bay_matrix.csv',index_col=0)
independent=pd.crosstab(production.STNFAM,production.BAY).reindex(index=matrix.index,columns=matrix.columns,fill_value=0)
check('entire 105x43 matrix independent reconciliation',np.array_equal(matrix.to_numpy(),independent.to_numpy()))
e=pd.read_csv(OUT/'tables/equipment_position_summary.csv')
for col in ['POSITION_X','POSITION_Y','WIDTH','HEIGHT']:
    check(col+' output exact source values',np.allclose(e.set_index('NAME')[col].loc[source.NAME],source[col].to_numpy(),atol=1e-8,rtol=0))
check('all equipment retained',set(source.NAME)==set(e.NAME) and len(e)==1116)
pngs=sorted((OUT/'figures').rglob('*.png'))
check('20 final figure pairs',len(pngs)==20)
dimensions=[]
for p in pngs:
    with Image.open(p) as im:
        check(p.stem+' nonblank',np.asarray(im.convert('RGB').resize((100,100))).std()>10)
        check(p.stem+' resolution',im.width>=2700 and im.height>=3240)
        dimensions.append({'file':p.relative_to(OUT).as_posix(),'width':im.width,'height':im.height})
    check(p.stem+' SVG pair',p.with_suffix('.svg').exists())
html=(OUT/'interactive/smat_layout_viewer.html').read_text(encoding='utf-8')
check('offline HTML no external assets',not re.search(r'<(?:script|link)[^>]+(?:src|href)=',html))
data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S).group(1))
check('viewer equipment exact IDs',set(d['NAME'] for d in data['equipment'])==set(source.NAME))
check('viewer rail count',len(data['rails'])==3424)
check('viewer endpoint direction sequence',[(d['FROM_NODE'],d['TO_NODE']) for d in data['rails']]==list(zip(tables['Rail'].FROM_NODE,tables['Rail'].TO_NODE)))
check('source XLSX SHA256 unchanged',hashlib.sha256((SRC/'SMAT_2022_Model_Data_-_LVHM_E.xlsx').read_bytes()).hexdigest()=='8e74e6db2272ad7dbeeb26de2adb1cd69e27a7848fe7baa0524803fd317156c0')
report=(OUT/'SMAT原始布局可视化与分析报告.md').read_text(encoding='utf-8')
for link in re.findall(r'\]\(([^)]+)\)',report):
    if not link.startswith(('http:','https:')):check('report link '+link,(OUT/link).exists())
for name in ['data_checks.json','browser_checks.json']:
    saved=json.loads((OUT/'validation'/name).read_text(encoding='utf-8'))
    rows=saved if isinstance(saved,list) else saved['checks']
    check(name+' all passed',all(x['passed'] for x in rows))
for collection,name,cols,w,h in [(sorted((OUT/'figures').glob('*.png')),'contact_overview',3,600,440),(sorted((OUT/'figures/selected_workcenters').glob('*.png')),'contact_workcenters',4,450,650)]:
    sheet=Image.new('RGB',(cols*w,((len(collection)+cols-1)//cols)*h),'white');draw=ImageDraw.Draw(sheet)
    for i,p in enumerate(collection):
        tile=ImageOps.contain(Image.open(p),(w-10,h-30));sheet.paste(tile,((i%cols)*w,(i//cols)*h+25));draw.text(((i%cols)*w+6,(i//cols)*h+6),p.stem,fill='black')
    sheet.save(OUT/'validation'/f'{name}.png')
(OUT/'validation/independent_checks.json').write_text(json.dumps({'alternate_reader':'openpyxl read_only','checks':checks,'figure_dimensions':dimensions},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed_independent_checks':len(checks),'figures':len(pngs),'tables':len(list((OUT/'tables').rglob('*.csv')))},ensure_ascii=False))
