import * as THREE from './vendor/three.module.min.js';
import {Spring} from './engine.mjs';

// Articulated illustrations: every visible character part is a zero-depth plane.
function paint(draw){
 const canvas=document.createElement('canvas');canvas.width=canvas.height=512;
 const c=canvas.getContext('2d');c.scale(256,256);c.translate(1,1);
 c.lineJoin='round';c.lineCap='round';draw(c);
 const map=new THREE.CanvasTexture(canvas);map.colorSpace=THREE.SRGBColorSpace;
 return new THREE.MeshBasicMaterial({map,transparent:true,alphaTest:.02,side:THREE.DoubleSide,depthWrite:true,toneMapped:false});
}
const fill=(c,color)=>{c.fillStyle=color;c.fill();c.strokeStyle='#28332f';c.lineWidth=.025;c.stroke();};
const body=paint(c=>{c.beginPath();c.moveTo(-.49,-.71);c.bezierCurveTo(-.83,-.45,-.87,.75,-.45,.86);c.quadraticCurveTo(0,.98,.49,.86);c.bezierCurveTo(.87,.75,.79,-.45,.45,-.71);c.closePath();fill(c,'#fffef5');});
const head=paint(c=>{
 c.beginPath();c.moveTo(-.67,-.36);c.lineTo(-.57,-.91);c.quadraticCurveTo(-.50,-1,-.27,-.57);c.quadraticCurveTo(.02,-.65,.28,-.51);c.lineTo(.62,-.92);c.quadraticCurveTo(.78,-1,.77,-.30);c.bezierCurveTo(1,.15,.77,.72,.30,.80);c.bezierCurveTo(-.05,.91,-.61,.63,-.71,.32);c.closePath();fill(c,'#fffef5');
 c.fillStyle='#e9e9da';c.beginPath();c.moveTo(.48,-.55);c.lineTo(.66,-.80);c.lineTo(.66,-.35);c.fill();
 c.fillStyle='#fffef5';c.beginPath();c.ellipse(-.47,.23,.47,.39,-.12,0,Math.PI*2);c.fill();
 c.fillStyle='#17231e';c.beginPath();c.ellipse(-.62,.14,.31,.29,-.12,0,Math.PI*2);c.fill();
 c.fillStyle='#ffffff';c.beginPath();c.ellipse(-.70,.045,.063,.035,-.4,0,Math.PI*2);c.fill();
 c.strokeStyle='#27352d';c.lineWidth=.025;c.beginPath();c.moveTo(-.44,.50);c.quadraticCurveTo(-.23,.64,-.06,.48);c.stroke();
});
const ink=paint(c=>{c.fillStyle='#25332c';c.beginPath();c.roundRect(-.22,-.94,.44,1.88,.22);c.fill();});
const hand=paint(c=>{c.fillStyle='#25332c';c.beginPath();c.ellipse(0,.05,.42,.56,-.15,0,Math.PI*2);c.fill();for(let i=0;i<3;i++){c.beginPath();c.roundRect(-.38+i*.24,-.78,.20,.8,.1);c.fill();}});
const eye=paint(c=>{c.fillStyle='#17231e';c.beginPath();c.ellipse(0,0,.25,.36,0,0,Math.PI*2);c.fill();});
const mouthMat=paint(c=>{c.fillStyle='#27352d';c.beginPath();c.ellipse(0,0,.7,.8,0,0,Math.PI*2);c.fill();});
function group(parent,x,y,z=0){const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);return g;}
function plane(parent,mat,w,h,x=0,y=0,z=0){const m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),mat);m.position.set(x,y,z);m.castShadow=true;parent.add(m);return m;}
export function makePaperCharacter(scene,role,position){
 const root=group(scene,position[0],.98,position[1]),torso=group(root,0,.54),headRig=group(torso,0,.93,.025);
 plane(torso,body,1.14,1.45,0,.18);plane(headRig,head,1.39,1.39,0,.09);
 const scarf=paint(c=>{c.fillStyle=role.color;c.beginPath();c.roundRect(-.68,-.20,1.36,.34,.16);c.fill();c.beginPath();c.moveTo(.27,.06);c.lineTo(.62,.65);c.lineTo(.23,.54);c.lineTo(.04,.06);c.fill();});
 plane(torso,scarf,1, .52,0,.71,.04);
 const eyes=[plane(headRig,eye,.15,.15,-.10,.23,.045),plane(headRig,eye,.15,.15,.41,.21,.045)];
 const mouth=plane(headRig,mouthMat,.09,.014,-.16,-.23,.05),arms=[];
 for(const side of [-1,1]){
  const shoulder=group(torso,side*.48,.55,.06),elbow=group(shoulder,0,-.43,.005),wrist=group(elbow,0,-.40,.005);
  plane(shoulder,ink,.19,.49,0,-.20);plane(elbow,ink,.17,.46,0,-.19);plane(wrist,hand,.24,.28,0,-.07,.005);arms.push({shoulder,elbow,wrist});
  plane(root,ink,.18,.64,side*.25,-.25,-.025);
 }
 const cupMat=paint(c=>{c.strokeStyle='#576b51';c.lineWidth=.09;c.beginPath();c.arc(.45,0,.29,-Math.PI/2,Math.PI/2);c.stroke();c.beginPath();c.moveTo(-.6,-.55);c.lineTo(.35,-.55);c.lineTo(.3,.6);c.lineTo(-.5,.6);c.closePath();fill(c,'#d4e2be');});
 const cup=plane(arms[1].wrist,cupMat,.37,.37,0,-.05,.03),pencil=plane(arms[1].wrist,ink,.035,.35,.08,-.09,.04);cup.visible=pencil.visible=false;
 const springs={};for(const key of ['lean','bodyYaw','headYaw','headPitch','headRoll','lsX','lsZ','leX','lwZ','rsX','rsZ','reX','rwZ'])springs[key]=new Spring();
 return {role,root,torso,head:headRig,eyes,mouth,arms,cup,pencil,springs,gesture:'listen',manual:null,anchor:new THREE.Vector3(),seed:Math.random()*10,paper:true};
}

export function animatePaper(a,s,t,speaking,camera){
 // Cylindrical billboard: illustration stands in world space, without spherical volume.
 a.root.rotation.y=Math.atan2(camera.position.x-a.root.position.x,camera.position.z-a.root.position.z);
 a.torso.rotation.set(0,0,s.lean*.45+Math.sin(t*.9+a.seed)*.009);
 a.torso.position.y=.54+Math.sin(t*1.7+a.seed)*.009;
 a.torso.scale.y=1+Math.sin(t*1.7+a.seed)*.005;
 a.head.rotation.set(0,0,s.headRoll+s.headPitch*.22);
 a.head.position.y=.93-s.headPitch*.08;a.head.scale.x=1-Math.abs(s.headYaw)*.12;
 a.arms.forEach((arm,i)=>{const side=i?1:-1,pre=i?'r':'l';arm.shoulder.rotation.set(0,0,s[pre+'sZ']+side*(-s[pre+'sX'])*.28);arm.elbow.rotation.set(0,0,side*(-s[pre+'eX'])*.65);arm.wrist.rotation.set(0,0,s[pre+'wZ']);});
 const phase=(t+a.seed*2)%5.1,blink=phase<.16?Math.sin(phase/.16*Math.PI)**2:0;
 a.eyes.forEach(e=>e.scale.y=1-.93*blink);a.mouth.scale.y=speaking?1+3*Math.sin(t*8.5)**2:1;
}
