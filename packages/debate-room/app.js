import {DebateScene} from './scene.js';
import {DebateEngine,roles,topics,gestures} from './engine.mjs';
import {CouncilClient} from './api-client.mjs';
const $=s=>document.querySelector(s),people=$('#people'),heads=$('#heads'),transcript=$('#transcript');
const view=new Map(),records=new Map(),gestureNames={listen:'安静倾听',explain:'展开解释',question:'歪头追问',open:'双手展开',point:'指向观点',think:'托腮思考',nod:'点头回应',disagree:'摇头异议',wave:'挥手招呼',write:'低头记录',sip:'举杯小憩',celebrate:'举手赞同'};
let scene,engine,toastTimer,previous,previewPaused=false;
const client=new CouncilClient();
const statusText=s=>({active:'讨论进行中',paused:'讨论已暂停',stopped:'讨论已停止',finished:'讨论已结束'}[s]||s||'讨论');
const speechSizer=new ResizeObserver(entries=>{for(const entry of entries){const id=entry.target.dataset.owner;const v=view.get(id);if(v)v.height=entry.borderBoxSize?.[0]?.blockSize||entry.contentRect.height+30;}});
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),2300);}
for(const role of roles){const person=document.createElement('button');person.className='person';person.dataset.role=role.id;person.setAttribute('aria-label',role.id==='user'?'聚焦你的发言框':`邀请${role.name}发言`);const avatar=document.createElement('span');avatar.className='avatar';avatar.style.background=role.color+'15';if(role.id!=='user'){const img=document.createElement('img');img.src='assets/kanshan-reference.jpg';img.alt='刘看山';img.style.cssText='width:30px;height:30px;object-fit:contain;border-radius:50%';avatar.appendChild(img);}else avatar.textContent='你';const words=document.createElement('span'),name=document.createElement('strong'),title=document.createElement('small');name.textContent=role.name;title.textContent=role.title;words.append(name,title);const bars=document.createElement('span');bars.className='speaking-bars';bars.innerHTML='<i></i><i></i><i></i>';person.append(avatar,words,bars);people.appendChild(person);
 const head=document.createElement('div');head.className='head-label';head.dataset.role=role.id;const speech=document.createElement('article');speech.className='speech';speech.setAttribute('aria-label',`${role.name}的头顶发言`);const who=document.createElement('small');who.textContent=role.name+' · 正在发言';who.style.color=role.color;const content=document.createElement('p'),text=document.createTextNode(''),cursor=document.createElement('span');cursor.className='typing-cursor';content.append(text,cursor);speech.append(who,content);const label=document.createElement('button');label.className='seat-name';label.textContent=role.name;label.setAttribute('aria-label',role.id==='user'?'我要发言':`请${role.name}继续`);head.append(speech,label);heads.append(head);view.set(role.id,{person,head,speech,content,text,cursor,label,role,chars:0});
 speech.dataset.owner=role.id;speechSizer.observe(speech);
 const invite=()=>{if(role.id==='user'){$('#message').focus();return;}engine.invite(role.id);if($('#motions').open)engine.paused=true;syncPause();};person.onclick=invite;label.onclick=invite;
 const option=document.createElement('option');option.value=role.id;option.textContent=role.name;$('#actor').appendChild(option);
}
function syncPause(){const p=engine.paused;scene?.setPaused(p);$('#pause').textContent=p?'▶':'Ⅱ';$('#pause').setAttribute('aria-label',p?'继续讨论':'暂停讨论');$('#discussion-status').textContent=p?'讨论已暂停':'讨论进行中';}
function record(m){let el=records.get(m.id);if(!el){el=document.createElement('article');el.className='transcript-item';const label=document.createElement('small');label.textContent=`${roles.find(r=>r.id===m.role).name} · 第 ${m.id} 次发言`;const body=document.createElement('p');el.append(label,body);transcript.appendChild(el);records.set(m.id,el);}el.querySelector('p').textContent=m.done?m.text:m.text.slice(0,m.visible);$('#message-count').textContent=engine.messages.length;}
function emit(kind,m){if(kind==='reset'){records.clear();transcript.replaceChildren();view.forEach(v=>{v.speech.classList.remove('show','past');v.person.classList.remove('live');v.text.nodeValue='';v.label.classList.remove('active');});previous=null;$('#topic-title').textContent=topics[m.topic].title;$('#topic-sub').textContent=topics[m.topic].sub;return;}
 if(kind==='turn'){if(previous){const old=view.get(previous);old.speech.classList.remove('show');old.speech.classList.add('past');old.person.classList.remove('live');old.label.classList.remove('active');}const v=view.get(m.role);v.text.nodeValue='';v.chars=m.text.length;v.speech.classList.remove('past');v.speech.classList.add('show');v.person.classList.add('live');v.label.classList.add('active');v.cursor.hidden=false;previous=m.role;scene?.setSpeaker(m.role,m.gesture);record(m);syncPause();}
 if(kind==='text'){const v=view.get(m.role);v.text.nodeValue=m.text.slice(0,m.visible);record(m);}
 if(kind==='settle'){const v=view.get(m.role);v.text.nodeValue=m.text;v.cursor.hidden=true;record(m);}
 if(kind==='user')toast('已发送，正在等大家回应…');
 if(kind==='error')toast('后端：'+m.message);
}
engine=new DebateEngine(emit,client);
client.onMessage=m=>engine.push(m);
client.onDiscussion=d=>{$('#discussion-status').textContent=statusText(d.status);};
client.onConnection=state=>{
 if(state==='reconnecting')toast('连接中断，正在重连…');
 if(state==='timeout')toast('连接到期，2 秒后自动续上…');
 if(state==='closed')toast('讨论已结束，记录已保存。');
};
try{scene=new DebateScene($('#scene'),roles,(id,x,y,w,h,show)=>{const v=view.get(id);v.head.hidden=!show;v.head.style.transform=`translate3d(${x}px,${y}px,0)`;v.label.style.transform='translateX(-50%)';const width=w<500?164:w<850?195:224;const bx=Math.max(width/2+10,Math.min(w-width/2-10,x));v.speech.style.left=(bx-x)+'px';v.speech.style.bottom='38px';v.speech.style.top='auto';});scene.onTick=dt=>{if(scene.ready)engine.tick(dt);};scene.onReady=()=>$('#loading').classList.add('ready');scene.onError=error=>{$('#loading').classList.add('ready');$('#scene-error').hidden=false;$('#scene-error').textContent='刘看山模型加载失败，请检查资源文件或刷新页面。';};}
catch(error){$('#loading').classList.add('ready');$('#scene-error').hidden=false;console.error(error);}

/* 连接后端：优先恢复上次的讨论，没有就新建一条。
   历史消息从服务端拉回来，所以刷新页面记录不会丢。 */
(async()=>{
 try{
  await client.ensureLogin();
  const saved=localStorage.getItem('debate.discussion');
  let discussion=null;
  if(saved){try{discussion=await client.load(saved);}catch(_){discussion=null;}}
  if(!discussion){discussion=await client.create(topics[0].title);}
  localStorage.setItem('debate.discussion',discussion.id);
  topics[0]={...topics[0],title:discussion.topic,sub:statusText(discussion.status)+' · 后端已连接'};
  engine.reset(0);
  const history=await client.history();
  history.forEach(m=>engine.push(m));
  if(!history.length)toast('已连接后端，说第一句话开始讨论。');
  $('#discussion-status').textContent=statusText(discussion.status);
  client.connect();
 }catch(error){
  console.error(error);
  toast('后端未连接：'+error.message);
 }
})();
$('#pause').onclick=()=>{engine.paused=!engine.paused;syncPause();};
$('#speed').onclick=()=>{const speeds=[.8,1,1.35];engine.speed=speeds[(speeds.indexOf(engine.speed)+1)%speeds.length];$('#speed').textContent=engine.speed+'×';};
$('#restart').onclick=async()=>{scene.stopPreview();try{const title=(topics[engine.topic]||topics[0]).title;const discussion=await client.create(title);localStorage.setItem('debate.discussion',discussion.id);engine.reset(engine.topic);$('#discussion-status').textContent=statusText(discussion.status);client.connect();syncPause();toast('新的讨论，从同一个问题出发。');}catch(error){toast('重开失败：'+error.message);}};
$('#compose').onsubmit=e=>{e.preventDefault();if(engine.submit($('#message').value)){ $('#message').value='';$('#message').style.height='auto';syncPause();}else{toast('先写下一句话，再把它放到桌上。');$('#message').focus();}};
$('#message').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#compose').requestSubmit();}});
$('#message').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(90,e.target.scrollHeight)+'px';});
$('#hand').onclick=()=>{scene.preview('user','wave');setTimeout(()=>{if(!$('#motions').open)scene.stopPreview();},2200);$('#message').focus();toast('把你的观点写下来，发出后就轮到你。');};
$('#history-open').onclick=()=>{$('#history').hidden=false;transcript.scrollTop=transcript.scrollHeight;};$('#history-close').onclick=()=>$('#history').hidden=true;
$('#export').onclick=async()=>{try{const items=await client.history();const text=`# ${topics[engine.topic].title}\n\n来自讨论室后端的持久化记录，共 ${items.length} 条。\n\n`+items.map(m=>`## ${(roles.find(r=>r.id===m.role_id)||{}).name||m.role_id}\n\n${m.body}`).join('\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='ThinkSpace-长桌讨论.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),5000);toast(`已导出 ${items.length} 条记录`);}catch(error){toast('导出失败：'+error.message);}};
$('#topic-open').onclick=()=>$('#topics').showModal();topics.forEach((topic,i)=>{const button=document.createElement('button');button.className='topic-option';const title=document.createElement('strong'),sub=document.createElement('small');title.textContent=topic.title;sub.textContent=topic.sub;button.append(title,sub);button.onclick=async()=>{scene.stopPreview();$('#topics').close();try{const discussion=await client.create(topics[i].title);localStorage.setItem('debate.discussion',discussion.id);engine.reset(i);$('#topic-open').hidden=false;$('#discussion-status').textContent=statusText(discussion.status);client.connect();syncPause();}catch(error){toast('创建讨论失败：'+error.message);}};$('#topic-list').appendChild(button);});
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#motion-open').onclick=()=>{previewPaused=engine.paused;engine.paused=true;syncPause();$('#stage').after($('#motions'));$('#motions').show();};$('#motions').addEventListener('close',()=>{scene.stopPreview();engine.paused=previewPaused;syncPause();});
gestures.forEach(gesture=>{const b=document.createElement('button');b.textContent=gestureNames[gesture];b.dataset.gesture=gesture;b.onclick=()=>{scene.preview($('#actor').value,gesture,true);$('#gesture-list').querySelectorAll('button').forEach(el=>el.classList.toggle('selected',el===b));toast(`${roles.find(r=>r.id===$('#actor').value).name} · ${gestureNames[gesture]}`);};$('#gesture-list').appendChild(b);});
$('#actor').onchange=()=>{const selected=$('#gesture-list button.selected');if(selected)scene.preview($('#actor').value,selected.dataset.gesture,true);};
let maxGap=0;setInterval(()=>{if(!scene)return;const s=scene.stats();$('#stats').textContent=`${s.actors} 位角色 · ${s.frames} 帧已绘制 · 预热后平均帧间隔 ${s.mean.toFixed(1)}ms · P95 ${s.p95.toFixed(1)}ms · 最近 600 帧 >50ms：${s.over50} · DPR ${s.dpr.toFixed(2)}`;$('#stats').dataset.frames=s.frames;$('#stats').dataset.p95=s.p95.toFixed(2);$('#stats').dataset.over50=s.over50;},1000);
let thoughtTopicIndex;
async function setThought(title, body) {
 const topicTitle = String(title).trim().slice(0, 180) || '来自资料库的思绪';
 try {
  await client.ensureLogin();
  const discussion = await client.create(topicTitle);
  localStorage.setItem('debate.discussion', discussion.id);
  thoughtTopicIndex ??= topics.length;
  topics[thoughtTopicIndex] = {
   title: topicTitle,
   sub: String(body || topicTitle).trim().slice(0, 180) || '来自资料库的思绪',
   turns: [],
  };
  engine.reset(thoughtTopicIndex);
  $('#topic-open').hidden = true;
  $('#discussion-status').textContent = statusText(discussion.status);
  client.connect();
  syncPause();
 } catch (error) {
  toast('创建讨论失败：' + error.message);
 }
}
window.debateRoom={setThought,setTopic:index=>{if(index>=0&&index<topics.length)engine.reset(index);},submit:text=>engine.submit(text),pause:()=>{engine.paused=true;syncPause();},resume:()=>{engine.paused=false;syncPause();},getTranscript:()=>engine.messages.map(m=>({...m})),dispose:()=>scene?.dispose()};
window.addEventListener('pagehide',()=>scene?.dispose(),{once:true});
