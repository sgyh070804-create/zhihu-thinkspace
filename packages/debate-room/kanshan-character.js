import * as THREE from './vendor/three.module.min.js';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {clone} from './vendor/utils/SkeletonUtils.js';
import {Spring} from './engine.mjs';

let sourcePromise;
const modelUrl=new URL('./assets/kanshan/kanshan-runtime.glb',import.meta.url);
export function loadKanshan(){return sourcePromise??=new GLTFLoader().loadAsync(modelUrl.href);}
export function makeKanshan(scene,role,position){
 const root=new THREE.Group();root.position.set(position[0],.26,position[1]);scene.add(root);
 const springs={};for(const key of ['lean','bodyYaw','headYaw','headPitch','headRoll','lsX','lsZ','leX','lwZ','rsX','rsZ','reX','rwZ'])springs[key]=new Spring();
 return {role,root,springs,kanshan:true,anchor:new THREE.Vector3(),gesture:'listen',manual:null,seed:Math.random()*10,bones:new Map(),cup:new THREE.Group(),pencil:new THREE.Group(),propBlend:new Spring(),loaded:false};
}
export function attachKanshan(actor,gltf){
 const model=clone(gltf.scene);model.scale.setScalar(.76);actor.root.add(model);actor.model=model;actor.eyes=[];
 model.updateMatrixWorld(true);
 model.traverse(o=>{
  if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}
  if(o.isBone){const rest=o.quaternion.clone(),world=o.getWorldQuaternion(new THREE.Quaternion());actor.bones.set(o.userData.name||o.name,{bone:o,rest,world,inverse:world.clone().invert()});}
 });
 for(const required of ['body','head','upper_arm.L','upper_arm.R','forearm.L','forearm.R','hand.L','hand.R']){if(!actor.bones.has(required))throw new Error('Missing Kanshan bone: '+required);}
 for(const label of ['L','R']){const b=actor.bones.get('leg.'+label);if(b)b.bone.scale.y=1.35;}
 const hand=actor.bones.get('hand.R')?.bone;
 if(hand){
  const mug=new THREE.Mesh(new THREE.CylinderGeometry(.16,.13,.29,20),new THREE.MeshStandardMaterial({color:0xf4f6f8,roughness:.5}));mug.position.set(.05,.05,.08);actor.cup.add(mug);
  const handle=new THREE.Mesh(new THREE.TorusGeometry(.10,.023,8,20),mug.material);handle.position.set(.21,.05,.08);actor.cup.add(handle);
  const pencil=new THREE.Mesh(new THREE.CylinderGeometry(.018,.018,.46,8),new THREE.MeshStandardMaterial({color:0x35495d,roughness:.6}));actor.pencil.add(pencil);actor.pencil.position.set(.03,.12,.08);actor.pencil.rotation.z=.5;
  hand.add(actor.cup,actor.pencil);actor.cup.visible=actor.pencil.visible=false;
 }
 actor.loaded=true;
}
const euler=new THREE.Euler(),delta=new THREE.Quaternion(),local=new THREE.Quaternion();
function rotate(actor,name,x=0,y=0,z=0){
 const b=actor.bones.get(name);if(!b)return;
 delta.setFromEuler(euler.set(x,y,z));local.copy(b.inverse).multiply(delta).multiply(b.world);b.bone.quaternion.copy(b.rest).multiply(local);
}
export function animateKanshan(actor,s,t,gesture,dt){
 if(!actor.loaded)return;
 actor.model.position.y=Math.sin(t*1.7+actor.seed)*.008;
 rotate(actor,'body',s.lean*.35,s.bodyYaw*.6,Math.sin(t*.9+actor.seed)*.006);
 rotate(actor,'head',s.headPitch*.65,s.headYaw*.65,s.headRoll*.7);
 for(const [label,prefix] of [['L','l'],['R','r']]){
  rotate(actor,'upper_arm.'+label,s[prefix+'sX']*.68,0,s[prefix+'sZ']*.8);
  rotate(actor,'forearm.'+label,s[prefix+'eX']*.85,0,0);
  rotate(actor,'hand.'+label,0,0,s[prefix+'wZ']*.8);
 }
 const prop=gesture==='sip'||gesture==='write',amount=actor.propBlend.step(prop?1:0,dt);
 actor.cup.visible=gesture==='sip'&&amount>.01;actor.pencil.visible=gesture==='write'&&amount>.01;
 actor.cup.scale.setScalar(Math.max(.001,amount));actor.pencil.scale.setScalar(Math.max(.001,amount));
}
