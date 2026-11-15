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
const {GLTFLoader}=await import(loader),{makeKanshan,attachKanshan,animateKanshan,kanshanPose}=await import(moduleUrl(actorSource));

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

// Test screen-space landmarks with the actual GLB and the narrow desktop camera,
// rather than accepting a changed quaternion that may still be hidden by the desk.
test('seated wave/open/celebration hands clear the desk and read at preview size',async()=>{
 const bytes=readFileSync(new URL('assets/kanshan/kanshan-runtime.glb',root));
 const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
 const a=makeKanshan(new THREE.Scene(),{id:'a'},[0,-2.35]);attachKanshan(a,gltf);a.seed=0;
 const camera=new THREE.OrthographicCamera(-7.75,7.75,7.75,-7.75,.1,80);
 camera.position.set(3.7,12,18);camera.lookAt(0,2.1,0);camera.updateMatrixWorld(true);
 const hand=(gesture,t,label='R')=>{animateKanshan(a,kanshanPose(gesture,t),t,gesture,1/60);a.root.updateMatrixWorld(true);return a.bones.get('hand.'+label).bone.getWorldPosition(new THREE.Vector3());};
 const project=v=>{const p=v.clone().project(camera);return new THREE.Vector2(p.x*250,p.y*250);};
 for(let i=0;i<60;i++){const w=hand('wave',i/30);assert.ok(w.x>1.0,'wave hand stays outside head silhouette');}
 const rest=hand('listen',0),wave=hand('wave',.3);
 assert.ok(wave.y>2.1,'wave stays well above the tabletop');
 assert.ok(project(wave).distanceTo(project(rest))>30,'raised hand moves >30px in a 500px viewport');
 for(const g of ['open','celebrate'])for(const label of ['L','R'])assert.ok(hand(g,.3,label).y>1.9,g+' hand must clear desk');
 const points=Array.from({length:60},(_,i)=>project(hand('wave',i/30)));
 const excursion=Math.max(...points.map(p=>p.x))-Math.min(...points.map(p=>p.x));
 assert.ok(excursion>7,'wave has a visible lateral sweep, not only wrist tremor');
 console.log('wave screen excursion at 500px:',excursion.toFixed(1),'px');
});

// Check the signed elbow side throughout spring-driven transitions, not only
// at hand-picked poses. An elbow must bulge away from the torso on both arms.
test('both elbows stay on their outward pole without stretching through all gesture transitions',async()=>{
 const bytes=readFileSync(new URL('assets/kanshan/kanshan-runtime.glb',root));
 const gltf=await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),'');
 const a=makeKanshan(new THREE.Scene(),{id:'a'},[0,-2.35]);attachKanshan(a,gltf);a.seed=0;
 const lengths=new Map();
 a.root.updateMatrixWorld(true);
 const point=name=>a.bones.get(name).bone.getWorldPosition(new THREE.Vector3());
 for(const label of ['L','R'])lengths.set(label,[point('upper_arm.'+label).distanceTo(point('forearm.'+label)),point('forearm.'+label).distanceTo(point('hand.'+label))]);
 let time=0,minOutside=Infinity;
 for(const gesture of ['listen','celebrate','open','wave','question','think','point','explain','disagree','write','sip','nod','listen']){
  for(let frame=0;frame<60;frame++){
   time+=1/60;const target=kanshanPose(gesture,time,true),s={};
   for(const key in target)s[key]=a.springs[key].step(target[key],1/60);
   animateKanshan(a,s,time,gesture,1/60);a.root.updateMatrixWorld(true);
   const body=a.bones.get('body'),rotation=body.bone.getWorldQuaternion(new THREE.Quaternion()).multiply(body.inverse);
   for(const label of ['L','R']){
    const shoulder=point('upper_arm.'+label),elbow=point('forearm.'+label),wrist=point('hand.'+label),line=wrist.clone().sub(shoulder).normalize();
    const deviation=elbow.clone().sub(shoulder);deviation.addScaledVector(line,-deviation.dot(line));
    const pole=new THREE.Vector3(label==='R'?1:-1,0,.18).applyQuaternion(rotation);
    const outside=deviation.dot(pole);minOutside=Math.min(minOutside,outside);
    assert.ok(outside>1e-5,gesture+' '+label+' elbow folded inward');
    assert.ok(Math.abs(shoulder.distanceTo(elbow)-lengths.get(label)[0])<1e-5,'upper arm stretched');
    assert.ok(Math.abs(elbow.distanceTo(wrist)-lengths.get(label)[1])<1e-5,'forearm stretched');
   }
  }
 }
 console.log('minimum outward elbow offset:',minOutside.toFixed(4));
});
