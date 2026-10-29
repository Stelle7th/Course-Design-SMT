// Adapt the final Week 6 reference slide in place, retaining its editable
// shapes, font sizes, colors, masters, layouts and exact canvas dimensions.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FileBlob,PresentationFile} from 'file:///C:/Users/WJH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const build=path.resolve(root,'../week7-ppt-build');
await fs.mkdir(build,{recursive:true});
const reference=path.join(root,'week6/汇报成稿/两Bay局部优化验证_收益解释版.pptx');
const presentation=await PresentationFile.importPptx(await FileBlob.load(reference));
const slide=presentation.slides.items[0];
if(presentation.slides.items.length!==1)throw new Error('Expected one reference slide');
const text={
 'slide-title':'全厂物流与加工仿真',
 'framing':'建立全厂物流与多工序加工模型，支持从总览逐级查看运输与排队。',
 'scope-heading':'仿真范围',
 'scope-body':'43 个 Bay、1,068 台生产设备、500 辆 OHT。',
 'scope-operations':'10 类产品、2,156 批初始在制品，运行 12 h。',
 'optimization-body':'采用原始轨道、端口和产品工艺路线。',
 'verification-heading':'调度与加工规则',
 'verification-gap':'搬运请求先到先服务，最近空闲车接货。',
 'verification-checks':'按设备组匹配资源，到达设备后排队加工。',
 'benefit-heading':'仿真运行过程',
 'benefit-scope':'请求搬运后，空车接货并装载运输。',
 'benefit-rate':'到达后卸载、排队，按工艺顺序加工。',
 'benefit-share':'加工完成后触发下一道工序的搬运。',
 'overall-heading':'交互查看与统计',
 'overall-formula':'按产品或工艺筛选，查看加粗运输路线。',
 'overall-scope':'查看加工进度、排队及运输等待指标。',
 'example-label':'按设备种类配色，跟踪车辆或单批物料。',
 'example-result':'支持暂停、倍速播放和多种镜头切换。',
 'OPEN_MILP_HTML':'打开全厂仿真 HTML',
 'validation-note':'当前使用原始参考布局，后续接入 MILP 重排对比。暂未模拟车辆避碰与轨道互斥。',
 'footer':'A2 组   第七周课程设计',
 'page-number':'1',
};
for(const [name,value]of Object.entries(text)){
 const shape=slide.shapes.items.find(s=>s.name===name);
 if(!shape)throw new Error('Missing template shape '+name);
 shape.text.replace(shape.text.toString(),value);
}
slide.speakerNotes.text=`【本页介绍，约 60 秒】
本周我们把设备布局扩展为全厂物流与多工序加工模型。模型沿用 SMAT2022 原始参考布局，包含 43 个 Bay，其中 40 个生产 Bay 和 3 个公共运输区域；有 1,068 台生产设备、48 个固定物流设施和 500 辆 OHT。物料采用 SMT2020 LVHM 的 10 类产品及 2,156 条初始 WIP，从各自 CURSTEP 开始推进后续工艺。运行窗口为 12 小时，另按常规订单 0.25 倍速率生成 10 批新物料。
物料请求搬运后，空车先到来源端口接货，装载后沿有向轨道运输，到达目标后卸载。若设备忙碌，物料在设备前排队；加工完成后触发下一道工序的运输。车辆在加工期间释放，可服务其他物料。产品使用共享设备网络，同一种工艺会在路线中反复出现。

【调度与加工规则】
搬运请求按全局先到先服务，选择沿有向轨道接货距离最近的空闲车。单车同时服务一批。设备必须满足工艺组兼容性，再根据未完成工作量和预计运输时间选择目标设备。物料实际到达后按先到先服务加工，单台机器同时加工一批。设备进出缓存假设无限，加工完成不因等候出站车而阻塞机器。
假设坐标单位为毫米，以恒速 1,500 mm/s 换算仿真时间，装载与卸载各 15 秒。每片加工按 25 片/lot 换算，批加工按代表批量折算为等效单 lot 机时，再除以 0.85。没有显式组批，Delay 步骤单独计时，不占用机器。

【点击链接后，按 HTML 演示，约 3 分钟】
先点“全厂运行”，按设备种类认识布局，再切运行状态看加工和队列。点“产品工艺”，单独看 part_5；粗紫线是截至当前时刻已派车任务的载货规划路线，重合路段合并，可取消“显示产品路线”。这不是产品独占的实体流水线，也没有凭空连接未来工序。
点“干刻资源”查看同类设备分布、精确设备组和共享队列。颜色相同只表示设备种类相同，不能据此任意替换加工设备。
点“回流批次”跟踪 Init_Lot_5_20：第 210 步在 A3 的 ECH0165 干刻，第 211 步到 B16 的 ECH0525 湿刻，第 212 步返回 A2 的 ECH0128 干刻。先用路径全景说明起终点，再用跟随镜头观察运输。
点“排队特写”查看 Init_Lot_5_12 第 213 步：约 160.22 min 到达 B15 的 ECH0499，约 177.03 min 才开始加工，等待约 16.81 min。使用设备特写先暂停讲解，再播放观察开始加工。

【当前结果及口径】
12 小时窗口内共完成 11,373 次搬运交付、9,333 次加工工序，11 批走完各自剩余路线并到达 COMPLETE。500 辆车全部参与过调度，实际开始过加工的设备为 1,061 台，不能把设备总数 1,068 写成全部都加工过。窗口结束时其他物料仍可能等待、运输或加工。这些是当前假设下的参考场景运行结果，不是 MILP 重排收益。

【模型边界】
WIP 没有提供具体初始设备和剩余加工时间，按上一道工序的兼容设备端口重建初始位置，会产生集中搬运波峰。原坐标单位和速度换算未现场校准。尚未模拟避碰、轨道互斥、ZCU、加减速、随机故障、维护、返工或抽检，因此资源等待不能解释为真实交通拥堵。本周定位为运行模型与交互观察环境，下一步将 A2/A3 的 MILP 重排位置接入同一套任务、车辆和调度规则，评价运输与排队变化。

【链接使用】
本 PPTX 与“全厂制造仿真.html”保存在 week7 同一目录。放映时点击紫色下划线链接，编辑时可 Ctrl+单击。移动或合并 PPT 后请保留同目录关系或重新设置链接。

【数据来源】
week7/factory/model.py；week7/factory/factory-data.json（config、metrics、recipes、lots、visits）；week7/README.md；week7/汇报演示建议.md。模板沿用 week6/汇报成稿/两Bay局部优化验证_收益解释版.pptx。
`;
const png=await presentation.export({slide,format:'png',scale:1});
await fs.writeFile(path.join(build,'week7-draft.png'),new Uint8Array(await png.arrayBuffer()));
const layout=await slide.export({format:'layout'});
await fs.writeFile(path.join(build,'week7-layout.json'),await layout.text());
await(await PresentationFile.exportPptx(presentation)).save(path.join(build,'authored.pptx'));
console.log(JSON.stringify({slides:presentation.slides.items.length,shapes:slide.shapes.items.length,template:reference,draft:path.join(build,'authored.pptx')}));
