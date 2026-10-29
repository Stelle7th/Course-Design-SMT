"""Set the local HTML hyperlink on the Artifact Tool authored slide."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT.parent / 'week7-ppt-build'
N = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
     'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
     'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
for prefix, uri in N.items():
    ET.register_namespace(prefix, uri)

with ZipFile(BUILD/'authored.pptx') as file:
    package = {name: file.read(name) for name in file.namelist()}
slide = ET.fromstring(package['ppt/slides/slide1.xml'])
rels = ET.fromstring(package['ppt/slides/_rels/slide1.xml.rels'])
hyperlinks = [r for r in rels if r.get('Type') == N['r']+'/hyperlink']
assert len(hyperlinks) == 1
hyperlinks[0].set('Target', '全厂制造仿真.html')
assert (ROOT/'week7/全厂制造仿真.html').is_file()
matches = 0
for shape in slide.findall('.//p:sp', N):
    nv = shape.find('p:nvSpPr/p:cNvPr', N)
    if nv is not None and nv.get('name') == 'OPEN_MILP_HTML':
        matches += 1
        for link in shape.findall('.//a:hlinkClick', N):
            link.set('tooltip', '打开全厂制造仿真')
        # The imported template already has shape- and run-level links.
        assert shape.findall('.//a:hlinkClick', N)
assert matches == 1
package['ppt/slides/slide1.xml'] = ET.tostring(slide, encoding='utf-8', xml_declaration=True)
package['ppt/slides/_rels/slide1.xml.rels'] = ET.tostring(rels, encoding='utf-8', xml_declaration=True)
with ZipFile(BUILD/'candidate.pptx', 'w', ZIP_DEFLATED) as file:
    for name, data in package.items():
        file.writestr(name, data)
print('Local demo link set to 全厂制造仿真.html')
