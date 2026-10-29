from pathlib import Path
import zipfile,xml.etree.ElementTree as ET,json,csv,posixpath
ROOT=Path(__file__).resolve().parent/'smat2022'
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def workbook_rows(path):
    z=zipfile.ZipFile(path)
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        strings=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
    rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    data={}
    for sheet in ET.fromstring(z.read('xl/workbook.xml')).findall('s:sheets/s:sheet',NS):
        target=rels[sheet.attrib['{'+NS['r']+'}id']]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        root=ET.fromstring(z.read(target));rows=[]
        for row in root.findall('s:sheetData/s:row',NS):
            cells={}
            for c in row.findall('s:c',NS):
                letters=''.join(x for x in c.attrib['r'] if x.isalpha());idx=0
                for x in letters:idx=idx*26+ord(x)-64
                v=c.find('s:v',NS);value=v.text if v is not None else ''
                if c.attrib.get('t')=='s':value=strings[int(value)]
                elif c.attrib.get('t')=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                cells[idx-1]=value or ''
            if cells and any(cells.values()):rows.append([cells.get(i,'') for i in range(max(cells)+1)])
        data[sheet.attrib['name']]=rows
    return data

if __name__=='__main__':
    for p in ROOT.glob('*.docx'):
        z=zipfile.ZipFile(p);n={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        body=ET.fromstring(z.read('word/document.xml')).find('w:body',n);lines=[]
        for item in body:
            if item.tag.endswith('}p'):lines.append(''.join(item.itertext()))
            elif item.tag.endswith('}tbl'):
                for tr in item.findall('w:tr',n):lines.append('\t'.join(''.join(tc.itertext()) for tc in tr.findall('w:tc',n)))
        p.with_suffix('.txt').write_text('\n'.join(lines),encoding='utf-8')
    data=workbook_rows(next(ROOT.glob('*.xlsx')))
    (ROOT/'tables.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    stats={}
    for name,rows in data.items():
        stats[name]={'nonempty_rows_including_header':len(rows),'headers':rows[0] if rows else [],'sample':rows[1:4]}
        with (ROOT/(name.replace('/','_')+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:csv.writer(f).writerows(rows)
    (ROOT/'sheet_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))
