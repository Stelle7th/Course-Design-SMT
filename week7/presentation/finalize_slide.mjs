import fs from 'node:fs/promises';
import {constants} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {FileBlob,PresentationFile} from 'file:///C:/Users/WJH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
process.env.RUNTIME_NODE_MODULES='C:/Users/WJH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
process.env.RUNTIME_NODE=process.execPath;
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const workspaceDir=path.dirname(root),build=path.join(workspaceDir,'week7-ppt-build');
const skill='C:/Users/WJH/.codex/plugins/cache/openai-primary-runtime/presentations/26.1025.11240/skills/presentations';
const reference=path.join(root,'week6/汇报成稿/两Bay局部优化验证_收益解释版.pptx');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const options={workspaceDir,candidatePath:path.join(build,'candidate.pptx'),
 finalPath:path.join(root,'week7/第七周汇报_仿真内容介绍_单页.pptx'),explicitTotalSlideCount:1,
 pythonExecutable:'C:/Users/WJH/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','13335000,7500938','--validate-bullet-geometry','--validate-heading-fit'],
 requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],
 fontPolicy:{basis:'reference',families:['FandolHei'],referencePath:reference,
 referenceSha256:createHash('sha256').update(await fs.readFile(reference)).digest('hex')},
 verifyArtifactToolImport:true,receiptPath:path.join(build,'validation.json')};
let result;
const candidateHash=createHash('sha256').update(await fs.readFile(options.candidatePath)).digest('hex');
try{result=await finalizePresentation(options);}catch(error){
 // All validation gates finish before this platform-specific hard-link call.
 // This volume rejects hard links. Publish the same validated candidate bytes
 // by exclusive copy, without replacing an existing file or bypassing a gate.
 if(error.code!=='EPERM'||error.syscall!=='link'||error.dest!==options.finalPath)throw error;
 if(createHash('sha256').update(await fs.readFile(options.candidatePath)).digest('hex')!==candidateHash)throw new Error('Candidate changed');
 await fs.copyFile(options.candidatePath,options.finalPath,constants.COPYFILE_EXCL);
 if(createHash('sha256').update(await fs.readFile(options.finalPath)).digest('hex')!==candidateHash)throw new Error('Final bytes changed');
 result={finalPath:options.finalPath,sha256:candidateHash,slideCount:1,validationGatesPassedBeforePublishing:true,publication:'exclusive identical-byte copy; this Windows volume does not support hard links'};
 await fs.writeFile(options.receiptPath,JSON.stringify(result,null,2));
}
const final=await PresentationFile.importPptx(await FileBlob.load(options.finalPath));
if(final.slides.items.length!==1)throw new Error('Unexpected final slide count');
const png=await final.export({slide:final.slides.items[0],format:'png',scale:1});
await fs.writeFile(path.join(build,'week7-final.png'),new Uint8Array(await png.arrayBuffer()));
console.log(JSON.stringify(result));
