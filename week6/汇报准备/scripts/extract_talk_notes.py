from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
folder=ROOT/'week6/汇报成稿';pptx=folder/'A2组_第六周周报_MILP.pptx'
text=['# 第六周 MILP 汇报讲稿','', '预计 6 分钟。第 3 页讲清边界，第 5 页展示六个变化槽位，第 6 页解释具体设备移动。','']
with ZipFile(pptx) as z:
    slides=sorted([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')],key=lambda n:int(n.split('slide')[-1].split('.')[0]))
    assert len(slides)==8
    for i in range(1,9):
        slide=ET.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
        labels=[e.text or '' for e in slide.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t')]
        title=labels[0]
        notes=ET.fromstring(z.read(f'ppt/notesSlides/notesSlide{i}.xml'))
        spoken='\n'.join(e.text or '' for e in notes.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'))
        spoken=spoken.split('数据来源：')[0].strip()
        text.extend([f'## 第 {i} 页：{title}','',spoken,''])
text.extend(['## 现场可能被问到的问题','',
 '问：0.582% 为什么不高？\n\n答：当前只允许现有槽位内的同尺寸、同工艺阶段交换，并固定区域承担的工序量和外部供需，优化自由度有限。这个小算例首先用于检验模型、可行性和最优性。','',
 '问：是不是全厂最优？\n\n答：是给定 A2、A3 槽位与固定生产边界下的数学最优解。全厂布局和动态拥堵不在这份最优性证书的范围内。','',
 '问：是否把一种机器改成另一种？\n\n答：设备类型保持不变。S0155、S0146 是固定槽位的名称，设备通过搬迁改变位置，使用目标槽位端口。各设备组和尺寸类别的总数守恒。','',
 '问：单个设备移动就贡献了 0.582% 吗？\n\n答：0.582% 是六台设备重排与加工物流联合优化的整体局部结果。LITH0213 到两个槽位的路径比较，只用于说明位置与端口怎样改变距离。','',
 '问：区域外工序去哪了？\n\n答：区域外生产通过每个外部源的供给、每个外部目标的接收量，以及区域工序加工量保留在边界中，没有直接删除外部工序。',''])
(folder/'逐页讲稿与答辩提示.md').write_text('\n'.join(text),encoding='utf-8')
print({'slides':len(slides),'notes':8,'pptx_bytes':pptx.stat().st_size})
