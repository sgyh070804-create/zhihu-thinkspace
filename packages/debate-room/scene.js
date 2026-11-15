import * as THREE from './vendor/three.module.min.js';
import {Spring} from './engine.mjs';
import {loadKanshan,makeKanshan,attachKanshan,animateKanshan} from './kanshan-character.js';
const V=THREE.Vector3;
const sphere=new THREE.SphereGeometry(1,28,20),capsule=new THREE.CapsuleGeometry(1,1,5,12);
const materials={white:new THREE.MeshStandardMaterial({color:0xfaf9f4,roughness:.83}),black:new THREE.MeshStandardMaterial({color:0x202522,roughness:.58}),nose:new THREE.MeshStandardMaterial({color:0x161b1a,roughness:.32}),skin:new THREE.MeshStandardMaterial({color:0xe8be9e,roughness:.82}),hair:new THREE.MeshStandardMaterial({color:0x303d4f,roughness:.95}),shirt:new THREE.MeshStandardMaterial({color:0x627b98,roughness:.94}),pants:new THREE.MeshStandardMaterial({color:0x48596f,roughness:.9}),paper:new THREE.MeshStandardMaterial({color:0xfdfcf3,roughness:.9})};
function mesh(geo,mat,parent,x=0,y=0,z=0,sx=1,sy=sx,sz=sx){const m=new THREE.Mesh(geo,mat);m.position.set(x,y,z);m.scale.set(sx,sy,sz);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
function ball(parent,mat,x,y,z,sx,sy=sx,sz=sx){return mesh(sphere,mat,parent,x,y,z,sx,sy,sz);}
function limb(parent,mat,len,r){return mesh(capsule,mat,parent,0,-len/2,0,r,len/3,r);}
function joint(parent,x,y,z){const g=new THREE.Group();g.position.set(x,y,z);parent.add(g);return g;}
function material(color){return new THREE.MeshStandardMaterial({color,roughness:.78});}
function rounded(w,d,h,r=.16){const s=new THREE.Shape(),x=-w/2,y=-d/2;s.moveTo(x+r,y);s.lineTo(x+w-r,y);s.quadraticCurveTo(x+w,y,x+w,y+r);s.lineTo(x+w,y+d-r);s.quadraticCurveTo(x+w,y+d,x+w-r,y+d);s.lineTo(x+r,y+d);s.quadraticCurveTo(x,y+d,x,y+d-r);s.lineTo(x,y+r);s.quadraticCurveTo(x,y,x+r,y);const g=new THREE.ExtrudeGeometry(s,{depth:h,bevelEnabled:true,bevelSegments:3,steps:1,bevelSize:.035,bevelThickness:.035,curveSegments:10});g.rotateX(-Math.PI/2);return g;}
function makeCharacter(scene,role,position,human=false){
 const root=new THREE.Group();root.position.set(position[0],.98,position[1]);root.rotation.y=human?Math.PI:0;scene.add(root);
 const torso=joint(root,0,.54,0),head=joint(torso,0,.91,0),hips=joint(root,0,.03,0);const white=human?materials.shirt:materials.white;
 ball(torso,white,0,.30,0,.51,.77,.39);ball(torso,white,0,-.12,.02,.48,.33,.37);
 if(human){ball(head,materials.skin,0,.08,0,.35,.40,.32);const hair=mesh(new THREE.SphereGeometry(.365,28,16,0,Math.PI*2,0,Math.PI*.63),materials.hair,head,0,.16,-.035,1,1,1);hair.rotation.x=-.1;ball(head,materials.skin,0,.07,.325,.065,.085,.08);ball(head,materials.skin,-.35,.08,0,.075,.11,.08);ball(head,materials.skin,.35,.08,0,.075,.11,.08);}
 else{ball(head,white,0,.05,0,.47,.52,.40);
  const earGeo=new THREE.LatheGeometry([new THREE.Vector2(0,0),new THREE.Vector2(.13,.015),new THREE.Vector2(.115,.13),new THREE.Vector2(.07,.32),new THREE.Vector2(.025,.43),new THREE.Vector2(0,.44)],18);
  mesh(earGeo,white,head,-.30,.34,-.045,1,1,1);mesh(earGeo,white,head,.30,.34,-.045,1,1,1);
  ball(head,white,0,-.04,.34,.34,.29,.32);ball(head,materials.nose,0,.035,.64,.29,.265,.25);
  ball(torso,white,0,-.03,-.40,.18,.19,.19);
  const collar=new THREE.Mesh(new THREE.TorusGeometry(.335,.065,8,40),material(role.color));collar.rotation.x=Math.PI/2;collar.position.set(0,.86,0);torso.add(collar);ball(torso,material(role.color),.18,.75,.34,.075,.15,.05);
 }
 const eyes=[ball(head,materials.black,-.225,.16,.35,.038,.048,.035),ball(head,materials.black,.225,.16,.35,.038,.048,.035)];
 const brows=[];if(human)for(const side of [-1,1]){const brow=mesh(new THREE.BoxGeometry(.13,.025,.02),materials.hair,head,side*.20,.25,.312);brow.rotation.z=side*.08;brows.push(brow);}
 const mouth=ball(head,materials.black,0,-.275,.53,.075,.012,.018);
 const arms=[];for(const side of [-1,1]){const shoulder=joint(torso,side*.49,.57,0),elbow=joint(shoulder,0,-.46,0);limb(shoulder,human?white:materials.black,.48,.085);ball(shoulder,human?white:materials.black,0,0,0,.10);limb(elbow,human?materials.skin:materials.black,.43,.07);const wrist=joint(elbow,0,-.42,0);ball(wrist,human?materials.skin:materials.black,0,-.055,0,.11,.14,.075);for(let j=0;j<3;j++){ball(wrist,human?materials.skin:materials.black,(j-1)*.055,-.16,.01,.032,.075,.035);}ball(wrist,human?materials.skin:materials.black,side*.10,-.05,.015,.04,.08,.04);arms.push({shoulder,elbow,wrist});}
 for(const side of [-1,1]){const hip=joint(hips,side*.23,0,.035);hip.rotation.x=-1.30;limb(hip,human?materials.pants:materials.black,.48,.105);const knee=joint(hip,0,-.47,0);knee.rotation.x=1.27;limb(knee,human?materials.pants:materials.black,.46,.087);ball(knee,materials.black,0,-.48,.07,.13,.10,.22);}
 const cup=joint(arms[1].wrist,0,-.09,.11);cup.visible=false;mesh(new THREE.CylinderGeometry(.13,.11,.25,20),material('#e4ebd8'),cup,0,-.02,0);const handle=mesh(new THREE.TorusGeometry(.09,.022,7,16),material('#d9e3ca'),cup,.14,-.02,0);handle.rotation.y=Math.PI/2;
 const pencil=mesh(new THREE.CylinderGeometry(.016,.016,.39,8),material('#bda774'),arms[1].wrist,0,-.10,.16);pencil.rotation.x=.9;pencil.visible=false;
 const springs={};for(const key of ['lean','bodyYaw','headYaw','headPitch','headRoll','lsX','lsZ','leX','lwZ','rsX','rsZ','reX','rwZ'])springs[key]=new Spring();
 return {role,root,torso,head,eyes,mouth,arms,springs,cup,pencil,gesture:'listen',manual:null,blend:new Spring(),anchor:new V(),blink:0,seed:Math.random()*10,human};
}
function pose(gesture,t,speaking){
 const swing=Math.sin(t*3.2),beat=Math.sin(t*5.5),p={lean:0,bodyYaw:0,headYaw:0,headPitch:0,headRoll:0,lsX:-.28,lsZ:-.12,leX:-.9,lwZ:0,rsX:-.28,rsZ:.12,reX:-.9,rwZ:0};
 switch(gesture){
 case 'explain':Object.assign(p,{lean:-.035,lsX:-.6,lsZ:-.42,leX:-1.2+.15*swing,lwZ:-.3,rsX:-.4,rsZ:.3,reX:-.9+.2*beat,rwZ:.25,headPitch:.045*swing});break;
 case 'open':Object.assign(p,{lsX:-.55,rsX:-.55,lsZ:-.72,rsZ:.72,leX:-1.2,reX:-1.2,lwZ:-.5,rwZ:.5,headRoll:.035*swing});break;
 case 'point':Object.assign(p,{rsX:-1.02,rsZ:.2,reX:-.45+.08*beat,rwZ:.4,lsX:-.3,headRoll:-.06,lean:-.06});break;
 case 'question':Object.assign(p,{headRoll:-.15,headPitch:-.06,lsX:-.3,rsX:-.9,rsZ:.32,reX:-1.8,rwZ:.3,bodyYaw:.03*swing});break;
 case 'think':Object.assign(p,{rsX:-.85,rsZ:.22,reX:-2.1,rwZ:-.1,headPitch:.15,headRoll:.12,lsX:-.35});break;
 case 'nod':Object.assign(p,{headPitch:.16*Math.sin(t*4.2),lsX:-.4,rsX:-.4,leX:-1.2,reX:-1.2});break;
 case 'disagree':Object.assign(p,{headYaw:.17*Math.sin(t*3),lsX:-.75,rsX:-.75,lsZ:-.5,rsZ:.5,leX:-.9,reX:-.9,lwZ:.7,rwZ:-.7});break;
 case 'wave':Object.assign(p,{rsX:-.2,rsZ:1.9,reX:-1.1,rwZ:.5*Math.sin(t*8),headRoll:-.1,lean:.025*swing});break;
 case 'write':Object.assign(p,{headPitch:.28,lean:-.12,lsX:-.65,leX:-.65,rsX:-.75+.04*beat,reX:-.7,rwZ:.14*Math.sin(t*12)});break;
 case 'sip':Object.assign(p,{rsX:-.8,rsZ:.05,reX:-2.05,rwZ:-.15,headPitch:-.05,lsX:-.4});break;
 case 'celebrate':Object.assign(p,{lsZ:-2.4,rsZ:2.4,lsX:-.15,rsX:-.15,leX:-.7,reX:-.7,headPitch:-.14,lean:.045*swing});break;
 case 'talk':Object.assign(p,{lsX:-.55,rsX:-.6,lsZ:-.32,rsZ:.4,leX:-1.15+.12*swing,reX:-1.1-.18*swing,headPitch:.05*beat});break;
 default:p.headPitch=.025*Math.sin(t*1.8);p.headRoll=.012*Math.sin(t*.6);
 }
 if(speaking){p.bodyYaw+=.025*Math.sin(t*1.6);p.lean+=.02*Math.sin(t*2.3);}return p;
}
function woodTexture(){const c=document.createElement('canvas');c.width=512;c.height=256;const ctx=c.getContext('2d');ctx.fillStyle='#c9d2df';ctx.fillRect(0,0,512,256);for(let i=0;i<150;i++){ctx.beginPath();ctx.strokeStyle=`rgba(78,97,125,${.015+(i%5)*.007})`;ctx.lineWidth=.5;for(let x=0;x<=512;x+=8){const y=i*2+Math.sin(x*.013+i)*1.6;x?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.stroke();}const texture=new THREE.CanvasTexture(c);texture.colorSpace=THREE.SRGBColorSpace;texture.wrapS=texture.wrapT=THREE.RepeatWrapping;texture.repeat.set(2,1);return texture;}
export class DebateScene{
 constructor(canvas,roles,onProject){this.canvas=canvas;this.roles=roles;this.onProject=onProject;this.actors=[];this.frames=[];this.active=null;this.time=0;this.last=0;this.frame=0;this.motionPreview=false;this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  this.renderer=new THREE.WebGLRenderer({canvas,antialias:true,alpha:false,powerPreference:'high-performance'});this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));this.renderer.setClearColor('#edf1f5');this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.18;
  this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#edf1f5');this.scene.fog=new THREE.Fog('#edf1f5',26,55);
  this.camera=new THREE.OrthographicCamera(-10,10,5,-5,.1,80);this.camera.position.set(5.0,9.2,16);this.camera.lookAt(0,2.4,0);
  const hemi=new THREE.HemisphereLight(0xf5f9ff,0x8191a6,2.6);this.scene.add(hemi);const key=new THREE.DirectionalLight(0xf0f5ff,3.0);key.position.set(-7,12,8);key.castShadow=true;key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-11,right:11,top:8,bottom:-8,near:.1,far:35});key.shadow.bias=-.0008;key.shadow.normalBias=.035;this.scene.add(key);const fill=new THREE.DirectionalLight(0xe3edff,.9);fill.position.set(7,5,-6);this.scene.add(fill);
  const floor=mesh(new THREE.PlaneGeometry(90,90),material('#edf1f5'),this.scene);floor.rotation.x=-Math.PI/2;floor.castShadow=false;floor.receiveShadow=true;
  const rug=mesh(rounded(17,9,.015,.9),material('#e4eaf1'),this.scene,0,.005,.5);rug.castShadow=false;
  const wood=new THREE.MeshStandardMaterial({color:0xc5cfdd,map:woodTexture(),roughness:.8});mesh(rounded(13.4,3.4,.22,.46),wood,this.scene,0,1.35,0);mesh(rounded(12.9,3,.14,.28),material('#9caabd'),this.scene,0,1.2,0);
  for(const x of [-5.5,5.5])for(const z of [-1.15,1.15]){const leg=mesh(new THREE.CylinderGeometry(.095,.075,1.28,12),material('#66788d'),this.scene,x,.64,z);leg.rotation.z=x>0?-.06:.06;}
  const placements=[[-4.4,-2.35],[0,-2.35],[4.4,-2.35],[0,2.8]];roles.forEach((r,i)=>{this.makeChair(placements[i],i===3);const actor=i===3?makeCharacter(this.scene,r,placements[i],true):makeKanshan(this.scene,r,placements[i]);this.actors.push(actor);this.makePlaceSetting(placements[i],i===3,r.color);});
  this.makeTableObjects();this.makePlant(7.7,-3.4);this.makePlant(-8,-1.5,.7);
  const ringMat=new THREE.MeshBasicMaterial({color:0x9fb2c8,transparent:true,opacity:.6,side:THREE.DoubleSide,depthWrite:false});this.ring=mesh(new THREE.RingGeometry(.68,.70,64),ringMat,this.scene,0,.035,0);this.ring.rotation.x=-Math.PI/2;this.ring.castShadow=false;
  this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(canvas.parentElement);this.resize();this.renderer.compile(this.scene,this.camera);this.running=true;this.ready=false;this.visibilityHandler=()=>{this.last=0;};document.addEventListener('visibilitychange',this.visibilityHandler);
  this.assetReady=false;this.warmFrames=0;loadKanshan().then(gltf=>{if(!this.running)return;this.actors.filter(a=>a.kanshan).forEach(a=>attachKanshan(a,gltf));this.assetReady=true;}).catch(error=>{console.error(error);this.onError?.(error);});
  this.loop=this.loop.bind(this);this.raf=requestAnimationFrame(this.loop);
 }
 makeChair(pos,human){const chair=new THREE.Group();chair.position.set(pos[0],0,pos[1]);chair.rotation.y=human?Math.PI:0;this.scene.add(chair);const mat=material(human?'#8093aa':'#b8c4d3');mesh(rounded(1.1,1.05,.10,.2),mat,chair,0,.86,0);const back=mesh(rounded(1.07,.14,.9,.13),mat,chair,0,1.0,-.52);for(const x of [-.41,.41])for(const z of [-.39,.39])mesh(new THREE.CylinderGeometry(.035,.027,.88,8),material('#7e8fa2'),chair,x,.43,z);}
 makePlaceSetting(pos,human,color){const g=new THREE.Group();g.position.set(pos[0],1.62,human?1.0:-.95);g.rotation.y=human?Math.PI:0;this.scene.add(g);const pad=mesh(rounded(.7,.56,.018,.045),material('#f4f6fa'),g,0,0,0);for(let i=0;i<4;i++)mesh(new THREE.BoxGeometry(.4,.004,.008),material('#d1d9e4'),g,-.03,.021,-.12+i*.075);mesh(new THREE.CylinderGeometry(.014,.014,.53,8),material(color),g,.42,.022,.03).rotation.z=Math.PI/2;const mug=mesh(new THREE.CylinderGeometry(.12,.10,.24,20),material(human?'#6c829a':'#f1f4f8'),g,-.57,.12,.08);const coffee=mesh(new THREE.CircleGeometry(.103,20),material('#5e6370'),g,-.57,.246,.08);coffee.rotation.x=-Math.PI/2;}
 makeTableObjects(){const g=new THREE.Group();g.position.set(-1.9,1.63,.1);this.scene.add(g);mesh(rounded(.85,.55,.1,.02),material('#8196af'),g,0,0,0);const book=mesh(rounded(.8,.5,.1,.02),material('#abbacf'),g,.06,.11,.03);book.rotation.y=.13;mesh(rounded(.7,.42,.018,.02),materials.paper,g,-.03,.22,0);const vase=mesh(new THREE.CylinderGeometry(.15,.21,.34,20),material('#dce3ed'),this.scene,2.3,1.80,0);for(let i=0;i<4;i++){const stem=mesh(new THREE.CylinderGeometry(.008,.008,.42,6),material('#7c929a'),this.scene,2.3+Math.sin(i)*.1,2.1,Math.cos(i)*.08);stem.rotation.z=Math.sin(i)*.3;const leaf=ball(this.scene,material('#99abb7'),2.3+Math.sin(i)*.17,2.29,Math.cos(i)*.11,.08,.18,.025);leaf.rotation.z=Math.sin(i)*.7;}}
 makePlant(x,z,scale=1){const g=new THREE.Group();g.position.set(x,0,z);g.scale.setScalar(scale);this.scene.add(g);mesh(new THREE.CylinderGeometry(.38,.28,.6,24),material('#d8e0e9'),g,0,.3,0);for(let i=0;i<9;i++){const a=i*2.399,h=.8+(i%3)*.3;const stem=mesh(new THREE.CylinderGeometry(.012,.012,h,6),material('#718a94'),g,Math.cos(a)*.1,h*.5+.5,Math.sin(a)*.1);stem.rotation.z=Math.cos(a)*.25;const leaf=ball(g,material(i%2?'#b2c0cb':'#92a8b5'),Math.cos(a)*.27,h+.4,Math.sin(a)*.27,.17,.39,.035);leaf.rotation.z=-Math.cos(a)*.65;leaf.rotation.y=a;}}
 resize(){this.width=this.canvas.parentElement.clientWidth;this.height=this.canvas.parentElement.clientHeight;this.renderHeight=Math.max(180,this.height-(this.width<680?65:95));const aspect=this.width/Math.max(1,this.renderHeight);const h=Math.max(8.2,15.5/aspect);this.camera.left=-h*aspect/2;this.camera.right=h*aspect/2;this.camera.top=h/2;this.camera.bottom=-h/2;this.camera.updateProjectionMatrix();if(aspect<1.25){this.camera.position.set(3.7,12,18);this.camera.lookAt(0,2.1,0);}else{this.camera.position.set(5,9.2,16);this.camera.lookAt(0,2.4,0);}this.renderer.setSize(this.width,this.height,false);this.renderer.setViewport(0,0,this.width,this.renderHeight);}
 setSpeaker(role,gesture){this.active=role;this.actors.forEach(a=>a.gesture=a.role.id===role?gesture:'listen');}
 preview(role,gesture){this.actors.forEach(a=>a.manual=a.role.id===role?gesture:'listen');this.motionPreview=true;}
 stopPreview(){this.actors.forEach(a=>a.manual=null);this.motionPreview=false;}
 updateActor(a,dt,t){const speaking=a.role.id===this.active&&!this.motionPreview;let gesture=a.manual||a.gesture;const idleCycle=Math.floor((t+a.seed)/8)%6;if(!speaking&&!a.manual){gesture=['listen','think','nod','listen','write','listen'][idleCycle];}
  const p=pose(gesture,t+a.seed,speaking),active=this.actors.find(x=>x.role.id===this.active);let look=0;if(active&&active!==a){const delta=active.root.position.clone().sub(a.root.position);const local=delta.applyAxisAngle(new V(0,1,0),-a.root.rotation.y);look=Math.max(-.42,Math.min(.42,Math.atan2(local.x,local.z)*.22));}
  if(a.kanshan&&gesture==='wave'){p.rsZ=3.25;p.rsX=-.12;p.reX=-.12;}
  p.headYaw+=look;const step=this.reduced?0:dt;
  for(const k in p)a.springs[k].step(p[k],step);const s=Object.fromEntries(Object.entries(a.springs).map(([k,v])=>[k,v.value]));
  if(a.kanshan){animateKanshan(a,s,this.reduced?0:t,gesture,dt);}else{
  a.torso.rotation.set(s.lean,s.bodyYaw,Math.sin(t*.9+a.seed)*.008);a.torso.position.y=.54+Math.sin(t*1.7+a.seed)*.009;a.torso.scale.y=1+Math.sin(t*1.7+a.seed)*.005;a.head.rotation.set(s.headPitch,s.headYaw,s.headRoll);
  a.arms[0].shoulder.rotation.set(s.lsX,0,s.lsZ);a.arms[0].elbow.rotation.x=s.leX;a.arms[0].wrist.rotation.z=s.lwZ;a.arms[1].shoulder.rotation.set(s.rsX,0,s.rsZ);a.arms[1].elbow.rotation.x=s.reX;a.arms[1].wrist.rotation.z=s.rwZ;
  const blinkPhase=(t+a.seed*2)%5.1,blink=blinkPhase<.16?Math.pow(Math.sin(blinkPhase/.16*Math.PI),2):0;a.eyes.forEach(e=>e.scale.y=.048*(1-.93*blink));a.mouth.scale.y=.012+(speaking?.055*Math.pow(Math.sin(t*8.5),2):0);}
  if(!a.kanshan){a.cup.visible=gesture==='sip';a.pencil.visible=gesture==='write';}
  a.root.updateMatrixWorld(true);a.anchor.set(0,a.kanshan?3.12:2.22,0).applyMatrix4(a.root.matrixWorld).project(this.camera);this.onProject(a.role.id,(a.anchor.x*.5+.5)*this.width,(-a.anchor.y*.5+.5)*this.renderHeight+(this.height-this.renderHeight),this.width,this.height);
 }
 loop(now){if(!this.running)return;this.raf=requestAnimationFrame(this.loop);const raw=(now-(this.last||now))/1000;this.last=now;if(document.hidden)return;const dt=Math.min(raw,.034);this.time+=dt;this.frame++;if(raw>0&&this.ready)this.frames.push(raw*1000);if(this.frames.length>600)this.frames.shift();this.actors.forEach(a=>this.updateActor(a,dt,this.time));const active=this.actors.find(a=>a.role.id===this.active);if(active){this.ring.position.x=active.root.position.x;this.ring.position.z=active.root.position.z;this.ring.material.opacity=.35+Math.sin(this.time*2)*.12;}
  this.renderer.render(this.scene,this.camera);if(this.assetReady)this.warmFrames++;if(!this.ready&&this.warmFrames>=16){this.ready=true;this.onReady?.();}this.onTick?.(dt);if(this.frame%180===0&&this.frames.length>120){const p=[...this.frames].sort((a,b)=>a-b)[Math.floor(this.frames.length*.95)];if(p>26&&this.renderer.getPixelRatio()>1){this.renderer.setPixelRatio(Math.max(1,this.renderer.getPixelRatio()-.25));this.renderer.setSize(this.width,this.height,false);this.renderer.setViewport(0,0,this.width,this.renderHeight);}}
 }
 stats(){const f=[...this.frames].sort((a,b)=>a-b);return {frames:this.frame,actors:this.actors.length,drawCalls:this.renderer.info.render.calls,triangles:this.renderer.info.render.triangles,p95:f.length?f[Math.floor(f.length*.95)]:0,mean:f.reduce((a,b)=>a+b,0)/Math.max(1,f.length),over50:f.filter(x=>x>50).length,dpr:this.renderer.getPixelRatio()};}
 dispose(){this.running=false;cancelAnimationFrame(this.raf);this.observer.disconnect();document.removeEventListener('visibilitychange',this.visibilityHandler);this.scene.traverse(o=>{if(o.geometry&&!['SphereGeometry','CapsuleGeometry'].includes(o.geometry.type))o.geometry.dispose();});this.renderer.dispose();}
}
