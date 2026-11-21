(function(global){
  'use strict';
  const physics=global.BubblePhysics||(typeof require==='function'?require('./bubble-physics.js'):null);if(!physics)throw Error('Load bubble-physics.js before thought-bubbles.js');
  const MAX=24, clamp=(v,a,b)=>Math.max(a,Math.min(b,v)), ease=t=>t*t*(3-2*t);
  const vertex='attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
  const fragment=`precision highp float;
  uniform vec2 size;uniform vec4 bubbles[24];uniform vec4 shapes[24];uniform vec4 contacts[24];uniform int count;uniform vec2 pair;uniform float clock;uniform float bridge;uniform sampler2D membrane;
  float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
  float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+1.),f.x),f.y);}
  float fbm(vec2 p){return noise(p)*.57+noise(p*2.03)*.28+noise(p*4.07)*.15;}
  mat2 rot(float a){return mat2(cos(a),-sin(a),sin(a),cos(a));}
  float node(float idx,float j){j=mod(j+64.,64.);vec2 rg=texture2D(membrane,vec2((j+.5)/65.,(idx+.5)/24.)).rg;return (dot(rg,vec2(256./257.,1./257.))-.5)/.9;}
  float membraneRadius(float idx,float theta){float u=fract(theta/6.2831853+1.)*64.,j=floor(u),f=fract(u);float a=node(idx,j-1.),b=node(idx,j),c=node(idx,j+1.),d=node(idx,j+2.);return 1.+.5*((2.*b)+(-a+c)*f+(2.*a-5.*b+4.*c-d)*f*f+(-a+3.*b-3.*c+d)*f*f*f);}
  vec2 local2(vec2 p,vec4 sh){return vec2(sh.x*p.x+sh.y*p.y,-sh.y*p.x+sh.x*p.y)*sh.zw;}
  float ellipsoid(vec3 p,vec4 b,float idx){vec2 q=(p.xy-b.xy)/b.z;float rho=membraneRadius(idx,atan(q.y,q.x));return (length(vec3(q/rho,p.z/b.z))-1.)*b.z*.78;}
  float smin(float a,float b,float k){float h=max(k-abs(a-b),0.)/k;return min(a,b)-h*h*k*.25;}
  vec4 ba;vec4 bb;vec4 sa;vec4 sb;
  float field(vec3 p){return smin(ellipsoid(p,ba,pair.x),ellipsoid(p,bb,pair.y),max(1.,min(ba.z,bb.z)*bridge));}
  vec3 environment(vec3 r,out float light){
    // Analytic studio: two rectangular softboxes, mullioned window, dark ceiling.
    vec2 u=vec2(atan(r.x,r.z),asin(clamp(r.y,-1.,1.)));
    float box1=(1.-smoothstep(.31,.40,abs(u.x+.72)))*(1.-smoothstep(.48,.58,abs(u.y+.32)));
    float box2=(1.-smoothstep(.075,.13,abs(u.x-1.15)))*(1.-smoothstep(.50,.65,abs(u.y-.10)));
    float window=(1.-smoothstep(.33,.40,abs(u.x+2.25)))*(1.-smoothstep(.32,.40,abs(u.y+.1)));
    float mullion=1.-.72*exp(-pow(sin((u.x+2.25)*13.)*8.,2.));window*=mullion;
    light=max(box1,max(box2,window));
    vec3 env=mix(vec3(.15,.18,.23),vec3(.68,.74,.82),smoothstep(-.65,.6,r.y));
    env+=vec3(.31,.24,.18)*pow(max(r.x,0.),3.);
    return mix(env,vec3(1.,.985,.96),clamp(box1*.96+box2*.85+window*.8,0.,1.));
  }
  void main(){vec2 p=vec2(gl_FragCoord.x,size.y-gl_FragCoord.y);float best=10000.;vec4 b=vec4(0.),sh=vec4(0.),contact=vec4(0.);int idx=0;
    for(int i=0;i<24;i++){if(i>=count)break;vec4 bi=bubbles[i];if(float(i)==pair.x){ba=bi;sa=shapes[i];}if(float(i)==pair.y){bb=bi;sb=shapes[i];}vec2 local=local2(p-bi.xy,shapes[i]);float distance=length(local);if(distance>bi.z*1.5+4.)continue;float d=distance-bi.z*membraneRadius(float(i),atan(local.y,local.x));if(d<best){best=d;b=bi;sh=shapes[i];contact=contacts[i];idx=i;}}
    if(best>max(3.,b.z*.20))discard;
    vec2 q=(p-b.xy)/b.z;float theta=atan(q.y,q.x),rho=membraneRadius(float(idx),theta);float r2=dot(q,q)/(rho*rho);vec3 n;float coverage=1.;bool liquid=false;
    if(pair.x>=0.&&bridge>.001){float bound=min(length(p-ba.xy)-ba.z*1.5,length(p-bb.xy)-bb.z*1.5);liquid=bound<0.&&(float(idx)==pair.x||float(idx)==pair.y);}
    if(liquid){float z=max(ba.z,bb.z)*1.65;vec3 pos=vec3(p,z);bool hit=false;
      for(int k=0;k<32;k++){float d=field(pos);if(d<.32){hit=true;break;}pos.z-=max(.35,d*.8);if(pos.z<0.)break;}
      if(!hit)discard;
      float e=.6;n=normalize(vec3(field(pos+vec3(e,0,0))-field(pos-vec3(e,0,0)),field(pos+vec3(0,e,0))-field(pos-vec3(0,e,0)),field(pos+vec3(0,0,e))-field(pos-vec3(0,0,e))));
      q=(p-(ba.xy+bb.xy)*.5)/max(ba.z,bb.z);r2=clamp(1.-n.z*n.z,0.,1.);
    }else{if(r2>1.015)discard;coverage=1.-smoothstep(.988,1.012,r2);float z=sqrt(max(.001,1.-r2));float dr=(membraneRadius(float(idx),theta+.025)-membraneRadius(float(idx),theta-.025))/.05;
    vec2 nn=q/(rho*rho)-dr/(rho*rho*rho)*vec2(-q.y,q.x);n=normalize(vec3(nn,z));}
    // Advected film thickness: domain-warped flow; geometric normals remain stable.
    float t=clock*.23;vec2 uv=q*1.7+vec2(float(idx)*.89,0.);
    vec2 flow=vec2(fbm(uv+vec2(t,-t*.7)),fbm(uv+vec2(4.,t*.55)));
    float film=fbm(uv+flow*2.6+vec2(-t*.4,t*.7));
    float ribbons=sin(q.y*9.+flow.x*8.-t*2.+sin(q.x*5.+t));
    float thickness=430.+film*190.+ribbons*38.+q.y*130.;
    vec3 interference=.5+.5*cos(12.56637*1.33*thickness*sqrt(1.-(1.-n.z*n.z)/1.7689)/vec3(650.,510.,475.));
    float disturbance=(film-.5)*.022; n=normalize(n+vec3(disturbance,-disturbance*.7,0.));
    vec3 reflected=reflect(vec3(0.,0.,-1.),n);float light;vec3 env=environment(reflected,light);
    float fresnel=.025+.975*pow(1.-max(n.z,0.),4.5);
    float rim=pow(1.-max(n.z,0.),13.);
    vec3 color=mix(vec3(.90,.91,.95),interference,.62);
    color=mix(color,env,clamp(.14+fresnel*.62+light*.65,0.,1.));
    color+=interference*rim*.18;
    float alpha=.028+fresnel*.80+light*(.38+.30*fresnel)+film*.035;
    // Tightly resolved dark grazing reflection and white surface glints.
    color=mix(color,vec3(.22,.24,.31),rim*.25);color=mix(color,vec3(1.),light*.7);
    gl_FragColor=vec4(color,clamp(alpha,0.,.91)*coverage*b.w);
  }`;
  function renderer(canvas){
    const gl=canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:false,powerPreference:'high-performance'});if(!gl)return null;
    const compile=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
    let program;try{program=gl.createProgram();const vs=compile(gl.VERTEX_SHADER,vertex),fs=compile(gl.FRAGMENT_SHADER,fragment);gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Shader link failed');}catch(e){console.warn('ThoughtBubbles: CSS fallback',e);return null;}
    gl.useProgram(program);const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);const a=gl.getAttribLocation(program,'p');gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);
    const u={};['size','bubbles[0]','count','pair','clock','shapes[0]','bridge','contacts[0]','membrane'].forEach(k=>u[k]=gl.getUniformLocation(program,k));const data=new Float32Array(MAX*4),shapeData=new Float32Array(MAX*4),contactData=new Float32Array(MAX*4);
    const texture=gl.createTexture();gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);const pixels=new Uint8Array(65*24*4);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,65,24,0,gl.RGBA,gl.UNSIGNED_BYTE,pixels);gl.uniform1i(u.membrane,0);
    return {draw(bs,w,h,pair,t,dpr,bridge,camera,focused){const pw=Math.round(w*dpr),ph=Math.round(h*dpr);if(canvas.width!==pw||canvas.height!==ph){canvas.width=pw;canvas.height=ph;gl.viewport(0,0,pw,ph);}data.fill(0);pixels.fill(128);bs.forEach((b,row)=>{const m=physics.ensure(b);for(let j=0;j<65;j++){const n=(row*65+j)*4;const value=Math.round((.5+m.offset[j%64]*.9)*65535);pixels[n]=value>>8;pixels[n+1]=value&255;pixels[n+3]=255;}});gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,texture);gl.texSubImage2D(gl.TEXTURE_2D,0,0,0,65,24,gl.RGBA,gl.UNSIGNED_BYTE,pixels);bs.forEach((b,i)=>data.set([(b.x*camera.scale+camera.x)*dpr,(b.y*camera.scale+camera.y)*dpr,b.r*b.scale*camera.scale*dpr,b.alpha*(b===focused?1:1-camera.amount*.90)],i*4));bs.forEach((b,i)=>shapeData.set([1,0,1,1],i*4));bs.forEach((b,i)=>contactData.set([b.cnx||0,b.cny||0,(b.contactDistance||b.r)*camera.scale*dpr,b.stress||0],i*4));gl.uniform4fv(u['contacts[0]'],contactData);gl.uniform4fv(u['shapes[0]'],shapeData);gl.uniform1f(u.bridge,bridge||0);gl.uniform2f(u.size,pw,ph);gl.uniform4fv(u['bubbles[0]'],data);gl.uniform1i(u.count,bs.length);gl.uniform2f(u.pair,pair[0],pair[1]);gl.uniform1f(u.clock,t);gl.drawArrays(gl.TRIANGLES,0,6);},destroy(){gl.deleteTexture(texture);gl.deleteBuffer(buffer);gl.deleteProgram(program);}};
  }
  function create(host,options={}){
    if(typeof host==='string')host=document.querySelector(host);if(!host)throw Error('ThoughtBubbles: container missing');
    const opts=Object.assign({items:[],maxDpr:1.35,speed:1,motionRate:1,onMerge:null,onSelect:null,onChange:null},options);
    const root=document.createElement('div');root.className='tb-space';root.style.cssText='width:100%;height:100%';host.appendChild(root);
    const scrim=document.createElement('div');scrim.className='tb-scrim';root.appendChild(scrim);
    const canvas=document.createElement('canvas');canvas.className='tb-canvas';canvas.setAttribute('aria-hidden','true');root.appendChild(canvas);
    const labels=document.createElement('div');labels.className='tb-labels';root.appendChild(labels);
    const hint=document.createElement('div');hint.className='tb-hint';hint.setAttribute('role','status');hint.setAttribute('aria-live','polite');root.appendChild(hint);
    const back=document.createElement('button');back.type='button';back.className='tb-back';back.textContent='回到思绪空间';back.hidden=true;root.appendChild(back);back.addEventListener('click',closeFocus);
    if(opts.externalReader)root.classList.add('tb-external-reader');
    let focused=null,viewed=null,focusStarted=0;const camera={x:0,y:0,scale:1,amount:0,vx:0,vy:0,vs:0,va:0};
    let render=renderer(canvas);if(!render)root.classList.add('tb-fallback');
    let bs=[],w=0,h=0,raf=0,last=0,time=0,drag=null,candidate=null,dwell=0,paused=false,dead=false,busy=false,anim=null,undoState=null,dirty=true,frames=[];
    const reduced=matchMedia('(prefers-reduced-motion: reduce)');
    const snapshot=()=>bs.map(b=>Object.assign({},b.item,{x:b.x/w,y:b.y/h}));
    function focus(id){if(busy||dead)return false;const b=bs.find(v=>v.item.id===id);if(!b)return false;focused=b;viewed=b;focusStarted=performance.now();bs.forEach(v=>{v.el.classList.toggle('tb-focused',v===b);v.el.style.pointerEvents=v===b&&!opts.externalReader?'auto':'none';v.el.tabIndex=v===b&&!opts.externalReader?0:-1;});root.classList.add('tb-inside');back.hidden=!!opts.externalReader;hint.textContent='在泡泡里，慢慢读 · 点击空白处或按 Esc 返回';dirty=true;opts.onFocusChange?.(Object.assign({},b.item));return true;}
    function closeFocus(){if(!focused)return;focused=null;bs.forEach(b=>{b.el.style.pointerEvents='';b.el.tabIndex=0;});back.hidden=true;hint.textContent='缓缓游动的想法 · 点击进入，拖动融合';dirty=true;opts.onFocusChange?.(null);}
    function selected(b){if(!focused){focus(b.item.id);opts.onSelect?.(Object.assign({},b.item));}}
    const keydown=e=>{if(e.key==='Escape')closeFocus();};root.addEventListener('keydown',keydown);
    root.addEventListener('click',e=>{if(focused&&performance.now()-focusStarted>450&&(e.target===root||e.target===canvas||e.target===labels))closeFocus();});
    function emit(){if(opts.onChange)opts.onChange(snapshot());}
    function resize(){w=root.clientWidth;h=root.clientHeight;bs.forEach(b=>{b.r=radius(b.item);b.x=clamp(b.x,b.r,w-b.r);b.y=clamp(b.y,b.r,h-b.r);});dirty=true;}
    function radius(item){return clamp(item.radius||Math.min(w,h)*.18,48,Math.min(200,w*.30,h*.30));}
    function add(item,i){if(bs.length>=MAX)throw Error('ThoughtBubbles: maximum 24 visible bubbles');if(!item.id||bs.some(b=>b.item.id===item.id))throw Error('ThoughtBubbles: ids must be unique and non-empty');
      const r=radius(item),angle=i*2.39996;const b={item:Object.assign({},item),r,x:clamp(item.x!=null?item.x*w:w*.5+Math.cos(angle)*w*.30,r,w-r),y:clamp(item.y!=null?item.y*h:h*.5+Math.sin(angle)*h*.29,r,h-r),vx:0,vy:0,seed:Math.random()*100,angle:0,squash:0,squashV:0,stress:0,textAlpha:1,scale:1,alpha:1,birth:item.generated||opts.animateEntrance?performance.now():null};
      const el=document.createElement('button');el.type='button';el.className='tb-bubble';el.setAttribute('aria-label',item.text+'。按 Enter 阅读。');
      if(item.generated){const tag=document.createElement('span');tag.className='tb-new';tag.textContent='新的观点';el.appendChild(tag);}
      const text=document.createElement('span');text.className='tb-thought';text.textContent=item.text;el.appendChild(text);const source=document.createElement('span');source.className='tb-source';source.textContent=item.source||'一颗思绪';el.appendChild(source);labels.appendChild(el);b.el=el;b.textEl=text;b.sourceEl=source;
      
      el.addEventListener('pointerdown',e=>{if(busy||focused||camera.amount>.1||drag||e.button!==0)return;const rect=root.getBoundingClientRect();drag={b,id:e.pointerId,ox:e.clientX-rect.left-b.x,oy:e.clientY-rect.top-b.y,sx:e.clientX,sy:e.clientY,px:e.clientX,py:e.clientY,pt:performance.now(),moved:false};b.vx=b.vy=0;el.setPointerCapture(e.pointerId);el.style.zIndex=3;});
      el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selected(b);}});
      physics.ensure(b);bs.push(b);dirty=true;return b;
    }
    function move(e){if(!drag||e.pointerId!==drag.id)return;const rect=root.getBoundingClientRect(),b=drag.b;drag.moved ||= Math.hypot(e.clientX-drag.sx,e.clientY-drag.sy)>4;const now=performance.now(),dt=Math.max(.008,(now-drag.pt)/1000);b.vx=clamp((e.clientX-drag.px)/dt,-500,500);b.vy=clamp((e.clientY-drag.py)/dt,-500,500);drag.px=e.clientX;drag.py=e.clientY;drag.pt=now;b.x=clamp(e.clientX-rect.left-drag.ox,b.r,w-b.r);b.y=clamp(e.clientY-rect.top-drag.oy,b.r,h-b.r);dirty=true;}
    function pickCandidate(a){let found=null,best=Infinity;for(const b of bs){if(b===a)continue;const gap=physics.gap(a,b);if(physics.capture(a,b,b===candidate)&&gap<best){found=b;best=gap;}}return found;}
    function release(e){if(!drag||drag.id!==e.pointerId)return;const {b,moved}=drag;const target=pickCandidate(b);b.el.style.zIndex='';drag=null;if(target&&moved){const other=target;candidate=null;dwell=0;merge(b.item.id,other.item.id).catch(()=>{});}else if(!moved)selected(b);candidate=null;dwell=0;dirty=true;}
    function cancel(){if(drag)drag.b.el.style.zIndex='';drag=null;candidate=null;dwell=0;dirty=true;}
    root.addEventListener('pointermove',move);root.addEventListener('pointerup',release);root.addEventListener('pointercancel',cancel);root.addEventListener('lostpointercapture',()=>{if(drag)cancel();});
    async function merge(idA,idB){
      if(busy||dead)throw Error('ThoughtBubbles: busy or destroyed');closeFocus();const a=bs.find(b=>b.item.id===idA),b=bs.find(b=>b.item.id===idB);if(!a||!b||a===b)throw Error('Select two distinct bubbles');
      if(!opts.onMerge){hint.textContent='请接入 onMerge 生成观点';throw Error('onMerge callback required');}
      busy=true;hint.textContent='正在连接两个想法…';dirty=true;
      try{const result=await opts.onMerge(Object.assign({},a.item),Object.assign({},b.item));if(dead)return;if(!result||!result.id||!result.text||bs.some(v=>v.item.id===result.id))throw Error('onMerge must return a new unique id and text');
        undoState=snapshot();const x=(a.x+b.x)/2,y=(a.y+b.y)/2;
        await new Promise(resolve=>{anim={a,b,x,y,ar:a.r,br:b.r,rr:Math.min(Math.cbrt(a.r**3+b.r**3),Math.min(w,h)*.29),phase:0,contactTime:0,neck:0,neckV:0,ax:a.x,ay:a.y,bx:b.x,by:b.y,elapsed:0,start:performance.now(),result,resolve};dirty=true;});
        if(!dead){hint.textContent='新的观点已形成 · 原想法可撤销恢复';emit();}
      }catch(e){if(!dead){hint.textContent='融合未完成，原想法已保留';opts.onError?.(e);}throw e;}finally{busy=false;dirty=true;}
    }
    function setItems(items){if(busy)throw Error('Cannot replace items during merge');if(items.length>MAX)throw Error('Maximum 24 visible bubbles');const ids=new Set();items.forEach(v=>{if(!v.id||ids.has(v.id))throw Error('Items require unique ids');ids.add(v.id);});closeFocus();viewed=null;undoState=null;bs.forEach(b=>b.el.remove());bs=[];cancel();items.forEach(add);dirty=true;}
    function tick(now){if(dead)return;raf=requestAnimationFrame(tick);const frameDt=(now-(last||now))/1000,dt=Math.min(frameDt,.035);last=now;if(document.hidden)return;
      if(!reduced.matches)time+=dt*opts.motionRate;if(frameDt>0)frames.push(frameDt);if(frames.length>120)frames.shift();let moving=!paused&&!reduced.matches;
      if(anim){const an=anim,step=dt*opts.motionRate;an.elapsed+=step;
        let dx=an.b.x-an.a.x,dy=an.b.y-an.a.y,sep=Math.hypot(dx,dy)||.001;const nx=dx/sep,ny=dy/sep,contact=an.ar+an.br;
        if(an.phase===0&&sep<contact*1.035){an.contactTime+=step;if(an.contactTime>.075)an.phase=1;}
        const rest=an.phase===0?contact*.995:0;
        // Spring pressure and surface attraction are integrated every frame.
        for(const [body,sign] of [[an.a,-1],[an.b,1]]){
          const tx=an.x+nx*rest*.5*sign,ty=an.y+ny*rest*.5*sign;
          body.vx+=((tx-body.x)*65-body.vx*15)*step;body.vy+=((ty-body.y)*65-body.vy*15)*step;
          body.x+=body.vx*step;body.y+=body.vy*step;
        }
        dx=an.b.x-an.a.x;dy=an.b.y-an.a.y;sep=Math.hypot(dx,dy);
        const joined=an.phase===1?clamp(1-sep/(contact*.995),0,1):0;
        const neckTarget=an.phase===1?clamp(joined*1.4,.06,.65):0;
        an.neckV+=((neckTarget-an.neck)*100-an.neckV*19)*step;an.neck=clamp(an.neck+an.neckV*step,0,.68);
        an.progress=an.phase===0?clamp(1-sep/(Math.hypot(an.bx-an.ax,an.by-an.ay)||contact),0,.30):.32+joined*.68;
        for(const [body,r0] of [[an.a,an.ar],[an.b,an.br]]){
          const targetR=r0+(an.rr-r0)*ease(joined);body.r+=(targetR-body.r)*Math.min(1,step*10);
          const pressure=Math.max(0,(contact-sep)/contact)*Math.max(0,1-an.neck/.65)*.75;
          
          body.angle=Math.atan2(dy,dx);body.stress=pressure;body.textAlpha=1-ease(clamp(joined*3,0,1));
        }
        an.a.cnx=nx;an.a.cny=ny;an.b.cnx=-nx;an.b.cny=-ny;an.a.contactDistance=Math.max(an.a.r*.65,sep*.5);an.b.contactDistance=Math.max(an.b.r*.65,sep*.5);dirty=true;
        if(reduced.matches||(an.phase===1&&sep<1.2&&Math.abs(an.a.r-an.rr)<.5&&Math.hypot(an.a.vx,an.a.vy)+Math.hypot(an.b.vx,an.b.vy)<3)){
          an.a.el.remove();an.b.el.remove();bs=bs.filter(b=>b!==an.a&&b!==an.b);const child=add(Object.assign({},an.result,{generated:true,radius:an.rr,x:an.x/w,y:an.y/h,parents:[an.a.item.id,an.b.item.id]}),bs.length);child.birth=null;child.reveal=performance.now();physics.impulse(child,.55,Math.atan2(dy,dx));anim=null;an.resolve();
        }
      }
      for(const b of bs){if(b.birth!==null){const t=reduced.matches?1:clamp((now-b.birth)/750,0,1);b.scale=.72+.28*ease(t);b.alpha=ease(t);dirty=true;if(t===1)b.birth=null;}}
      for(const b of bs){if(b.reveal){b.textAlpha=ease(clamp((now-b.reveal)/650,0,1));if(b.textAlpha===1)b.reveal=null;}if(!anim||(b!==anim.a&&b!==anim.b)){b.stress=0;b.cnx=0;b.cny=0;b.contactDistance=b.r;}}
      if(moving){for(const b of bs){if(drag?.b===b||(anim&&(b===anim.a||b===anim.b)))continue;b.vx+=(Math.sin(time*.35+b.seed)*4.5-b.vx*.8)*dt;b.vy+=(Math.cos(time*.29+b.seed*1.3)*4-b.vy*.8)*dt;b.x+=b.vx*dt*opts.speed;b.y+=b.vy*dt*opts.speed;}}
      {for(let i=0;i<bs.length;i++)for(let j=i+1;j<bs.length;j++){
        const a=bs[i],b=bs[j];if(anim&&(a===anim.a||a===anim.b||b===anim.a||b===anim.b))continue;const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||.01,nx=dx/d,ny=dy/d,gap=a.r+b.r,penetration=gap-d;
        if(penetration>0){const contact=Math.min(.33,penetration/gap*.9);a.stress=Math.max(a.stress,contact);b.stress=Math.max(b.stress,contact);a.angle=b.angle=Math.atan2(dy,dx);a.cnx=nx;a.cny=ny;b.cnx=-nx;b.cny=-ny;a.contactDistance=Math.max(a.r*.55,a.r-penetration*.45);b.contactDistance=Math.max(b.r*.55,b.r-penetration*.45);
          const deliberate=drag&&(drag.b===a||drag.b===b);const force=penetration*(deliberate?4:22);const rel=(b.vx-a.vx)*nx+(b.vy-a.vy)*ny;const impulse=Math.max(0,force-rel*2)*dt;
          if(!deliberate){a.vx-=nx*impulse;a.vy-=ny*impulse;b.vx+=nx*impulse;b.vy+=ny*impulse;}
        }}
        for(const b of bs){if(anim&&(b===anim.a||b===anim.b))continue;b.vx=clamp(b.vx,-220,220);b.vy=clamp(b.vy,-220,220);if(paused){b.vx*=Math.exp(-dt*8);b.vy*=Math.exp(-dt*8);}if(drag?.b!==b){const ex=b.r*1.02,ey=b.r*1.02;if(b.x<ex){b.x=ex;b.vx=Math.abs(b.vx)*.65;b.angle=0;b.stress=.1;}if(b.x>w-ex){b.x=w-ex;b.vx=-Math.abs(b.vx)*.65;}if(b.y<ey){b.y=ey;b.vy=Math.abs(b.vy)*.65;}if(b.y>h-ey){b.y=h-ey;b.vy=-Math.abs(b.vy)*.65;}}}
      }
      physics.solve(bs,reduced.matches?0:dt*opts.motionRate,{width:w,height:h},anim&&anim.neck>.001?[anim.a,anim.b]:null);
      const targetScale=focused?clamp(Math.min(w,h)*.405/focused.r,1.1,4.5):1;
      const targets={scale:targetScale,x:focused?w*.5-focused.x*targetScale:0,y:focused?h*.52-focused.y*targetScale:0,amount:focused?1:0};
      for(const [k,vk] of [['x','vx'],['y','vy'],['scale','vs'],['amount','va']]){if(reduced.matches){camera[k]=targets[k];camera[vk]=0;}else{camera[vk]+=((targets[k]-camera[k])*64-camera[vk]*16)*dt;camera[k]+=camera[vk]*dt;}}
      if(!focused&&camera.amount<.005){viewed=null;root.classList.remove('tb-inside');bs.forEach(b=>b.el.classList.remove('tb-focused'));}
      scrim.style.opacity=clamp(camera.amount,0,1)*.86;
      if(camera.amount>.001||Math.abs(camera.scale-1)>.001)dirty=true;
      if(!reduced.matches)dirty=true;
      if(drag){const next=pickCandidate(drag.b);if(candidate!==next){candidate=next;dwell=0;}if(next)dwell+=dt;hint.textContent=next?'已接触 · 松手融合':'拖到另一颗泡泡边缘即可融合';dirty=true;}
      if(!busy&&!drag&&!hint.textContent)hint.textContent='缓缓游动的想法 · 拖动靠近，融合新观点';
      if(dirty){const pair=anim?[bs.indexOf(anim.a),bs.indexOf(anim.b)]:[-1,-1];render?.draw(bs,w,h,pair,time,Math.min(devicePixelRatio||1,opts.maxDpr),anim?anim.neck:0,camera,viewed);for(const b of bs){const diameter=Math.round(b.r*camera.scale*2*10)/10;if(b.diameter!==diameter){b.el.style.width=b.el.style.height=diameter+'px';b.diameter=diameter;}const cx=b.x*camera.scale+camera.x,cy=b.y*camera.scale+camera.y;const zoom=b.scale;
        b.el.style.transform='translate3d('+(cx-b.r*camera.scale)+'px,'+(cy-b.r*camera.scale)+'px,0) scale('+zoom+')';
        b.el.style.opacity=b.alpha*b.textAlpha*(opts.externalReader?Math.pow(1-clamp(camera.amount,0,1),3):b===viewed?1:1-camera.amount*.96);
        b.el.style.zIndex=b===viewed?'5':'';
        const text=b.textEl,source=b.sourceEl;
        if(!opts.externalReader){text.style.fontSize=b===viewed?(16+4*camera.amount)+'px':'';source.style.fontSize=b===viewed?'11px':'';text.style.color=b===viewed?'rgb('+[52,53,69].map((v,i)=>Math.round(v+([241,238,248][i]-v)*camera.amount)).join(',')+')':'';
        text.style.maxHeight=b===viewed?(b.r*camera.scale*1.15)+'px':'';}}dirty=false;}
    }
    canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();render=null;root.classList.add('tb-fallback');});
    const observer=new ResizeObserver(resize);observer.observe(root);resize();setItems(opts.items);raf=requestAnimationFrame(tick);
    return {focus,closeFocus,merge,setItems,getItems:snapshot,seekMerge(progress){if(!anim)return false;const a=anim,p=clamp(progress,0,.99),dx=a.bx-a.ax,dy=a.by-a.ay,d=Math.hypot(dx,dy)||1,sep=(a.ar+a.br)*(1-p);a.a.x=a.x-dx/d*sep*.5;a.a.y=a.y-dy/d*sep*.5;a.b.x=a.x+dx/d*sep*.5;a.b.y=a.y+dy/d*sep*.5;a.a.vx=a.a.vy=a.b.vx=a.b.vy=0;a.phase=p>.32?1:0;a.neck=p>.32?clamp((p-.32)/.40,0,1)*.65:0;a.neckV=0;a.progress=p;dirty=true;return true;},setMotionRate(rate){opts.motionRate=clamp(Number.isFinite(Number(rate))?Number(rate):1,0,2);},pause(){paused=true;},resume(){paused=false;dirty=true;},undo(){if(!undoState||busy)return false;const previous=undoState;undoState=null;setItems(previous);hint.textContent='已恢复融合前的想法';emit();return true;},getStats(){return{renderer:render?'WebGL':'CSS',count:bs.length,reducedMotion:reduced.matches,mergeProgress:anim?.progress??null,averageFps:frames.length/frames.reduce((a,b)=>a+b,0),busy,focusedId:focused?.item.id??null};},destroy(){dead=true;cancelAnimationFrame(raf);observer.disconnect();if(anim)anim.resolve();render?.destroy();root.remove();}};
  }
  global.ThoughtBubbles={create};if(typeof module!=='undefined')module.exports=global.ThoughtBubbles;
})(typeof window!=='undefined'?window:globalThis);









