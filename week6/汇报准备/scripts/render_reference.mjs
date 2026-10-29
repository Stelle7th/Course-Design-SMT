import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/HP/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const source=String.raw`D:\Program Files\Tencent\Documents\WeChat_chat_records\xwechat_files\wxid_mvh4ywkw59io22_feaa\msg\file\2026-10\第六周汇报_正文前三页_兼容版.pptx`;
const out=String.raw`F:\Grade4\课程设计\analysis\week6_review\one_slide_build\reference`;
const p=await PresentationFile.importPptx(await FileBlob.load(source));
for(let i=0;i<p.slides.items.length;i++){
  const b=await p.export({slide:p.slides.items[i],format:'png',scale:1});
  await fs.writeFile(`${out}/reference-${i+1}.png`,new Uint8Array(await b.arrayBuffer()));
}
console.log('Rendered '+p.slides.items.length+' reference slides');
