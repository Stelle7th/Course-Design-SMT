from pathlib import Path
import sys, json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'analysis/a2_audit'))
from audit_smat import workbook_rows

raw = workbook_rows(ROOT/'analysis/a2_audit/smat2022/SMAT_2022_Model_Data_-_LVHM_E.xlsx')
tables = {k: pd.DataFrame([r+['']*(len(v[0])-len(r)) for r in v[1:]], columns=v[0]) for k,v in raw.items()}
for k,d in tables.items():
    print(k, len(d), 'duplicate names',d.NAME.duplicated().sum())
e=tables['Equipment']; a=tables['Address']; r=tables['Rail']; p=tables['Port']
for d in (e,a):
    for c in ['POSITION_X','POSITION_Y','WIDTH','HEIGHT']:
        if c in d:d[c]=pd.to_numeric(d[c])
print('ranges', e[['POSITION_X','POSITION_Y','WIDTH','HEIGHT']].agg(['min','max']).to_dict())
print('curves',r.CURVE.value_counts().to_dict(),'port types',p.PORT_TYPE.value_counts().to_dict())
print('dimension pairs',e.groupby(['WIDTH','HEIGHT']).size().to_dict())
print('B1',e[e.BAY=='B1'].head(8).to_dict('records'))
print('Inter rails',r[r.BAY_NAME.str.startswith('Inter')].head(12).to_dict('records'))
print('B1 nodes',a[a.NAME.str.startswith('rn_B1_')].head(10).to_dict('records'))
print('sample ports',p[p.EQP_NAME==e[e.BAY=='B1'].iloc[0].NAME].to_dict('records'))
