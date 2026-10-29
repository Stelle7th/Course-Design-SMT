"""Add the relative local-file hyperlink unsupported by the slide authoring API."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET
import json

ROOT=Path(__file__).resolve().parents[3]
BUILD=ROOT/'analysis'/'week6_review'/'one_slide_build'
BUILD.mkdir(exist_ok=True)
EXPORT=Path(r'C:\Users\HP\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Roaming\Codex\web\Codex\artifact-sessions\exports\latest\1c61cdba4e82bfa1cb447eb06c269c1785849c464075922f857b20ab781c329b')
SOURCE=EXPORT/'two-bay-one-slide-linked-base.pptx'
TARGET=BUILD/'candidate.pptx'
HTML=ROOT/'week6'/'汇报成稿'/'MILP交互展示.html'
assert HTML.is_file()
N={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
for prefix,uri in N.items(): ET.register_namespace(prefix,uri)
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
with ZipFile(SOURCE) as z:
    data={n:z.read(n) for n in z.namelist()}
slide=ET.fromstring(data['ppt/slides/slide1.xml'])
rels=ET.fromstring(data['ppt/slides/_rels/slide1.xml.rels'])
rid='rIdMilpHtml'
ET.SubElement(rels,f'{{{PKG}}}Relationship',{'Id':rid,'Type':N['r']+'/hyperlink','Target':'MILP交互展示.html','TargetMode':'External'})
matches=[]
for shape in slide.findall('.//p:sp',N):
    name=shape.find('p:nvSpPr/p:cNvPr',N)
    if name is not None and name.get('name')=='OPEN_MILP_HTML':
        ET.SubElement(name,f'{{{N["a"]}}}hlinkClick',{f'{{{N["r"]}}}id':rid,'tooltip':'打开两 Bay MILP 交互展示'})
        for run in shape.findall('.//a:r',N):
            props=run.find('a:rPr',N)
            if props is None: props=ET.Element(f'{{{N["a"]}}}rPr');run.insert(0,props)
            ET.SubElement(props,f'{{{N["a"]}}}hlinkClick',{f'{{{N["r"]}}}id':rid,'tooltip':'打开两 Bay MILP 交互展示'})
        matches.append(name.get('name'))
assert len(matches)==1, matches
data['ppt/slides/slide1.xml']=ET.tostring(slide,encoding='utf-8',xml_declaration=True)
data['ppt/slides/_rels/slide1.xml.rels']=ET.tostring(rels,encoding='utf-8',xml_declaration=True)
notes=ET.fromstring(data['ppt/notesSlides/notesSlide1.xml'])
for node in notes.findall('.//a:t',N):
    if node.text: node.text=node.text.replace('紫色链接','下划线链接')
data['ppt/notesSlides/notesSlide1.xml']=ET.tostring(notes,encoding='utf-8',xml_declaration=True)
with ZipFile(TARGET,'w',ZIP_DEFLATED) as z:
    for name,value in data.items(): z.writestr(name,value)
note_text='\n'.join(n.text or '' for n in notes.findall('.//a:t',N))
assert '实际路径为什么变短' in note_text
assert 'ECH0163' in note_text
assert len([n for n in data if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==1
(BUILD/'hyperlink-check.json').write_text(json.dumps({'slide_count':1,'hyperlink_shape':matches[0],'target':'MILP交互展示.html','target_exists':True,'speaker_notes_present':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(TARGET)
