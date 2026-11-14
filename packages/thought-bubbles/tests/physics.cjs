const assert=require('node:assert/strict');
const P=require('../dist/bubble-physics.js');
const b=(id,x,y=200)=>({id,x,y,r:100});
let a=b('a',200),c=b('b',401);
assert(P.capture(a,c),'1px contact tolerance should capture');c.x=404;assert(!P.capture(a,c),'4px clear gap must not capture');
// Two bubbles pressed together: direct integration, no stored poses.
c.x=385;for(let i=0;i<120;i++)P.solve([a,c],1/240);
const contact=P.ensure(a).offset[0],side=P.ensure(a).offset[16];
assert(contact<-.025,'contact side should indent');assert(side>0,'pressure should bulge the free side');
const before=Array.from(a.membrane.offset);c.x=600;
P.solve([a,c],1/240);assert(Math.abs(a.membrane.offset[0]-before[0])<.02,'recovery must not snap');
const energy=x=>Array.from(x.membrane.offset).reduce((s,v)=>s+v*v,0)+Array.from(x.membrane.velocity).reduce((s,v)=>s+v*v/65,0);
const e0=energy(a);for(let i=0;i<960;i++)P.solve([a,c],1/240);const e1=energy(a);
assert(e1<e0*.05,'released oscillation should dissipate');
console.log(JSON.stringify({captureAtGap1px:true,rejectAtGap4px:true,contactIndentPx:contact*100,freeSideBulgePx:side*100,recoveryEnergyRatio:e1/e0,nodeCount:P.N}));

