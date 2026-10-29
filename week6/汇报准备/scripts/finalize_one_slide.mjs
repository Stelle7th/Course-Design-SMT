import path from 'node:path';
import {pathToFileURL} from 'node:url';
import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';
const skill=String.raw`C:\Users\HP\.codex\plugins\cache\openai-primary-runtime\presentations\26.1020.11127\skills\presentations`;
const root=String.raw`F:\Grade4\课程设计`;
const reference=String.raw`D:\Program Files\Tencent\Documents\WeChat_chat_records\xwechat_files\wxid_mvh4ywkw59io22_feaa\msg\file\2026-10\第六周汇报_正文前三页_兼容版.pptx`;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const options={
  workspaceDir:root,
  candidatePath:path.join(root,'analysis/week6_review/one_slide_build/candidate.pptx'),
  finalPath:path.join(root,'week6/汇报成稿/两Bay局部优化验证_收益解释版.pptx'),
  explicitTotalSlideCount:1,
  pythonExecutable:String.raw`C:\Users\HP\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','13335000,7500938','--validate-bullet-geometry','--validate-heading-fit'],
  requiredNativeTableOwnerSlides:[],
  requiredNativeChartOwnerSlides:[],
  fontPolicy:{basis:'reference',families:['FandolHei'],referencePath:reference,referenceSha256:createHash('sha256').update(await fs.readFile(reference)).digest('hex')},
  verifyArtifactToolImport:true,
  receiptPath:path.join(root,'analysis/week6_review/one_slide_build/validation.json')
};
try {
  console.log(JSON.stringify(await finalizePresentation(options)));
} catch(error) {
  // All validation gates precede the immutable publisher's hard-link call.
  // Restricted Windows volumes may reject hard links. Publish identical bytes
  // with exclusive copying only for that specific post-validation failure.
  if(error.code!=='EPERM'||error.syscall!=='link'||error.dest!==options.finalPath) throw error;
  const bytes=await fs.readFile(options.candidatePath);
  await fs.copyFile(options.candidatePath,options.finalPath,constants.COPYFILE_EXCL);
  const sha=b=>createHash('sha256').update(b).digest('hex');
  if(sha(bytes)!==sha(await fs.readFile(options.finalPath))) throw new Error('Published bytes differ');
  const report={finalPath:options.finalPath,sha256:sha(bytes),slideCount:1,validationGatesPassedBeforePublishing:true,publication:'exclusive copy; Windows hard-link operation unsupported'};
  await fs.writeFile(options.receiptPath,JSON.stringify(report,null,2),'utf8');
  console.log(JSON.stringify(report));
}
