import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from '../vendor/three.module.min.js';

// Resolve browser import-map paths for Node without altering the modules' behavior.
const root=new URL('../',import.meta.url),three=new URL('vendor/three.module.min.js',root).href;
const moduleUrl=text=>'data:text/javascript;base64,'+Buffer.from(text).toString('base64');
const source=path=>readFileSync(new URL(path,root),'utf8');
const resolveThree=text=>text.replaceAll("from 'three'",`from '${three}'`);
const utils=moduleUrl(resolveThree(source('vendor/utils/BufferGeometryUtils.js')));
const loader=moduleUrl(resolveThree(source('vendor/GLTFLoader.js')).replace("'./utils/BufferGeometryUtils.js'",JSON.stringify(utils)));
const skeleton=moduleUrl(resolveThree(source('vendor/utils/SkeletonUtils.js')));
const actorSource=source('kanshan-character.js').replace("'./vendor/three.module.min.js'",JSON.stringify(three)).replace("'./vendor/GLTFLoader.js'",JSON.stringify(loader)).replace("'./vendor/utils/SkeletonUtils.js'",JSON.stringify(skeleton)).replace("'./engine.mjs'",JSON.stringify(new URL('engine.mjs',root).href)).replace("new URL('./assets/kanshan/kanshan-runtime.glb',import.meta.url)",`new URL('${new URL('assets/kanshan/kanshan-runtime.glb',root).href}')`);
const {GLTFLoader}=await import(loader),{makeKanshan,attachKanshan,animateKanshan}=await import(moduleUrl(actorSource));

test('GLTF loader binds original bone names and each seated actor moves independently',async()=>{
 const bytes=readFileSync(new URL('assets/kanshan/kanshan-runtime.glb',root));
 const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
 const scene=new THREE.Scene(),a=makeKanshan(scene,{id:'a'},[0,0]),b=makeKanshan(scene,{id:'b'},[4,0]);
 attachKanshan(a,gltf);attachKanshan(b,gltf);
 assert.equal(a.bones.size,11);assert.equal(b.bones.size,11);assert.notEqual(a.bones.get('upper_arm.R').bone,b.bones.get('upper_arm.R').bone);
 const original=b.bones.get('upper_arm.R').bone.quaternion.clone();
 const pose={lean:0,bodyYaw:0,headPitch:0,headYaw:0,headRoll:0,lsX:0,lsZ:0,leX:0,lwZ:0,rsX:-.12,rsZ:3.25,reX:-.12,rwZ:.3};
 animateKanshan(a,pose,1,'wave',1/60);
 assert.ok(a.bones.get('upper_arm.R').bone.quaternion.angleTo(original)>1);
 assert.deepEqual(b.bones.get('upper_arm.R').bone.quaternion.toArray(),original.toArray());
 assert.ok(a.loaded&&b.loaded);
});
