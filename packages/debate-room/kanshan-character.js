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
// Calibrated in the imported model's world axes, in radians. The short arms
// must clear the tabletop; these targets do not reuse the human avatar poses.
export function kanshanPose(gesture,t,speaking=false){
 const slow=Math.sin(t*2.4),beat=Math.sin(t*4.2),p={lean:0,bodyYaw:0,headYaw:0,headPitch:.035*Math.sin(t*1.6),headRoll:.025*slow,lsX:-.3,lsZ:-.4,leX:-.65,lwZ:0,rsX:-.3,rsZ:.4,reX:-.65,rwZ:0};
 switch(gesture){
 case 'explain':Object.assign(p,{lean:-.07,lsX:-.65,lsZ:-1.3-.28*slow,leX:-.85+.28*beat,lwZ:-.35,rsX:-.6,rsZ:1.05+.25*slow,reX:-1.05-.25*beat,rwZ:.35,headPitch:.10*slow});break;
 case 'open':Object.assign(p,{lsX:-.35,rsX:-.35,lsZ:-1.8-.17*slow,rsZ:1.8+.17*slow,leX:-.35,reX:-.35,lwZ:-.4,rwZ:.4,headRoll:.06*slow});break;
 case 'point':Object.assign(p,{rsX:-.65,rsZ:1.6+.16*slow,reX:-.18+.12*beat,rwZ:.3,headYaw:.14,headRoll:-.08,lean:-.09});break;
 case 'question':Object.assign(p,{headRoll:-.25+.07*slow,headPitch:-.08,rsX:-.75,rsZ:1.25+.25*slow,reX:-1.65+.15*beat,rwZ:.5,bodyYaw:.06*slow});break;
 case 'think':Object.assign(p,{rsX:-1.0,rsZ:.46,reX:-1.65,rwZ:-.15,headPitch:.22+.055*slow,headRoll:.16,bodyYaw:-.06});break;
 case 'nod':Object.assign(p,{headPitch:.34*Math.sin(t*3.5),lean:.06*Math.sin(t*3.5),lsX:-.6,rsX:-.6,leX:-1,reX:-1});break;
 case 'disagree':Object.assign(p,{headYaw:.42*Math.sin(t*2.8),lsX:-.65,rsX:-.65,lsZ:-1.15,rsZ:1.15,leX:-.6,reX:-.6,lwZ:.5,rwZ:-.5,bodyYaw:.06*Math.sin(t*2.8)});break;
 case 'wave':Object.assign(p,{rsX:-.12,rsZ:1.95+.28*Math.sin(t*4.7),reX:-.25+.14*slow,rwZ:.55*Math.sin(t*6.2),headRoll:-.10,bodyYaw:.05*slow});break;
 case 'write':Object.assign(p,{headPitch:.34,lean:-.13,lsX:-1.0,leX:-.5,rsX:-1.25+.12*beat,rsZ:.32,reX:-.3+.12*slow,rwZ:.30*Math.sin(t*7)});break;
 case 'sip':Object.assign(p,{rsX:-1.15,rsZ:.26,reX:-1.45+.12*slow,rwZ:-.25,headPitch:-.12+.06*slow,lsX:-.45});break;
 case 'celebrate':Object.assign(p,{lsZ:-2.3-.15*beat,rsZ:2.3+.15*beat,lsX:-.15,rsX:-.15,leX:-.2,reX:-.2,headPitch:-.16,lean:.06*slow});break;
 case 'talk':return kanshanPose('explain',t,speaking);
 }
 if(speaking){p.bodyYaw+=.055*Math.sin(t*1.6);p.lean+=.035*Math.sin(t*2.3);}return p;
}

const euler=new THREE.Euler(),delta=new THREE.Quaternion(),local=new THREE.Quaternion();
function rotate(actor,name,x=0,y=0,z=0){
 const b=actor.bones.get(name);if(!b)return;
 delta.setFromEuler(euler.set(x,y,z));local.copy(b.inverse).multiply(delta).multiply(b.world);b.bone.quaternion.copy(b.rest).multiply(local);
}
export function animateKanshan(actor,s,t,gesture,dt){
 if(!actor.loaded)return;
 actor.model.position.y=Math.sin(t*1.7+actor.seed)*.016;
 rotate(actor,'body',s.lean,s.bodyYaw,Math.sin(t*.9+actor.seed)*.006);
 rotate(actor,'head',s.headPitch,s.headYaw,s.headRoll);
 for(const [label,prefix] of [['L','l'],['R','r']]){
  rotate(actor,'upper_arm.'+label,s[prefix+'sX'],0,s[prefix+'sZ']);
  rotate(actor,'forearm.'+label,s[prefix+'eX'],0,0);
  rotate(actor,'hand.'+label,0,0,s[prefix+'wZ']);
 }
 const prop=gesture==='sip'||gesture==='write',amount=actor.propBlend.step(prop?1:0,dt);
 actor.cup.visible=gesture==='sip'&&amount>.01;actor.pencil.visible=gesture==='write'&&amount>.01;
 actor.cup.scale.setScalar(Math.max(.001,amount));actor.pencil.scale.setScalar(Math.max(.001,amount));
}
