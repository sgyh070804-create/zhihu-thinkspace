export const roles=[
 {id:'explorer',name:'探索者',title:'寻找另一种可能',color:'#5e8f7d',gesture:'explain'},
 {id:'skeptic',name:'质疑者',title:'给观点一点阻力',color:'#b98768',gesture:'question'},
 {id:'weaver',name:'归纳者',title:'把线索连成观点',color:'#9689ad',gesture:'open'},
 {id:'user',name:'你',title:'这张桌子的一员',color:'#3e665a',gesture:'talk'}
];
export const gestures=['listen','explain','question','open','point','think','nod','disagree','wave','write','sip','celebrate'];
export const topics=[
 {title:'AI 应该替我们做决定吗？',sub:'效率、判断与人的自主权',turns:[
 ['explorer','explain','如果 AI 能帮我们看见更多选择，决定会不会反而更自由？我想先区分：替我们分析，和替我们决定。'],
 ['skeptic','question','但选择摆在眼前，也可能已经经过筛选。我们真的知道，哪些选项被悄悄拿走了吗？'],
 ['weaver','open','你们说的是两个层面：一个是能力的扩展，一个是决定权的归属。也许关键在于，人能否理解并拒绝建议。'],
 ['explorer','point','那我们试一个具体情境：规划旅行可以交给 AI，但选择和谁一起去，应该留给自己。边界是否取决于价值判断？'],
 ['skeptic','disagree','我还想追问：如果我们习惯了每次都接受最优建议，独立判断会不会慢慢退化？方便也有代价。'],
 ['weaver','think','可以把原则暂时写成：让 AI 扩大可选范围，让人保留最终决定，并且能说清楚为什么。你会把边界画在哪里？']
 ]},
 {title:'读得更多，还是想得更深？',sub:'信息摄入与真正的理解',turns:[
 ['explorer','open','广泛阅读给我们更多连接的机会。一本看起来无关的书，也许正好解开另一个领域的问题。'],
 ['skeptic','question','但读过不等于理解。如果只是不断收藏和划线，我们可能只是把信息搬到了另一个地方。'],
 ['weaver','explain','一个可试的方法是：每读完一段，留一个自己的问题。用问题把输入变成下一步思考。'],
 ['explorer','point','也可以在两种不同观点之间搭桥。不是急着选边，而是找出它们各自在什么条件下成立。'],
 ['skeptic','think','我同意放慢一点。真正困难的可能是：愿不愿意承认自己刚才并没有读懂。'],
 ['weaver','nod','那今天的共识是：读的数量提供材料，主动提问和反复回看，才把材料变成理解。你的阅读习惯是什么？']
 ]},
 {title:'学习应该追求答案，还是问题？',sub:'确定性与探索的价值',turns:[
 ['explorer','explain','答案能带来确定感，但一个好问题，常常能让我们走到还没有地图的地方。'],
 ['skeptic','point','也不能一直提问却不验证。问题如果没有边界，探索就容易变成绕圈。'],
 ['weaver','open','也许把它看成循环更合适：提出问题，尝试回答，再用证据修正原来的问题。'],
 ['explorer','wave','所以我想邀请你试着提一个具体问题。我们一起拆开它，看看里面藏着哪些假设。'],
 ['skeptic','question','而我会负责问：这个答案如何被证明是错的？如果不能检验，我们真的学到了什么？'],
 ['weaver','nod','问题负责打开方向，答案负责建立落点。下一轮学习，可能就从两者之间的张力开始。']
 ]}
];
export class Spring{
 constructor(value=0){this.value=value;this.velocity=0;}
 step(target,dt,k=85,damping=18){const n=Math.max(1,Math.ceil(dt/0.008));const h=dt/n;for(let i=0;i<n;i++){this.velocity+=((target-this.value)*k-this.velocity*damping)*h;this.value+=this.velocity*h;}return this.value;}
}
export class DebateEngine{
 constructor(emit=()=>{}){this.emit=emit;this.topic=0;this.speed=1;this.paused=false;this.messages=[];this.index=0;this.current=null;this.elapsed=0;this.wait=0;this.serial=0;this.userQueue=[];}
 reset(topic=this.topic){this.topic=topic;this.messages=[];this.index=0;this.current=null;this.elapsed=0;this.wait=0;this.userQueue=[];this.paused=false;this.emit('reset',{topic});this.next();}
 next(){let turn;if(this.userQueue.length){turn=['user','talk',this.userQueue.shift()];}else{const list=topics[this.topic].turns;turn=list[this.index%list.length];if(this.index>=list.length){const variants=[['explorer','explain','我们换一个角度继续：如果把刚才的原则放到日常生活里，最先遇到的例外会是什么？'],['skeptic','question','我想保留一点不同意见。我们可以拿一个反例，检查刚才的共识是否足够稳固。'],['weaver','open','先把目前的线索放在桌面上：哪些是事实，哪些是判断，哪些仍然需要验证？']];turn=variants[(this.index-list.length)%variants.length];}this.index++;}
 this.start(...turn);}
 start(role,gesture,text){if(this.current&&!this.current.done){this.current.done=true;this.current.visible=this.current.text.length;this.emit('settle',this.current);}
 const m={id:++this.serial,role,gesture,text,visible:0,done:false};this.current=m;this.messages.push(m);this.elapsed=0;this.wait=0;this.emit('turn',m);return m;}
 tick(dt){if(this.paused||!this.current)return;this.elapsed+=dt*this.speed;const m=this.current;const count=Math.min(m.text.length,Math.floor(this.elapsed*20));if(count!==m.visible){m.visible=count;this.emit('text',m);}if(m.visible===m.text.length){if(!m.done){m.done=true;this.emit('settle',m);}this.wait+=dt*this.speed;if(this.wait>2.1)this.next();}}
 submit(text){const value=String(text).trim().slice(0,300);if(!value)return false;this.paused=false;this.start('user','talk',value);this.emit('user',this.current);return true;}
 invite(role){if(!roles.some(r=>r.id===role)||role==='user')return false;const variants={explorer:'我想沿着你刚才的问题，再打开一种可能。先别急着下结论，我们可以从最小的具体情境开始。',skeptic:'我先替这个观点找一个反例。它在哪些情况下可能失效？把边界说清楚，讨论才更有价值。',weaver:'我来把桌上的想法梳理一下：我们已经看见了不同立场，接下来可以比较它们共享的前提。'};this.paused=false;this.start(role,roles.find(r=>r.id===role).gesture,variants[role]);return true;}
}
