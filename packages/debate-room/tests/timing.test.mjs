import test from 'node:test';
import assert from 'node:assert/strict';
import {frameDelta} from '../timing.mjs';
import {Spring} from '../engine.mjs';
test('visible low-FPS frames preserve elapsed time and spring convergence',()=>{
 for(const fps of [1,15,30,60,144]){
  const s=new Spring();let elapsed=0;
  for(let i=0;i<fps*2;i++){const dt=frameDelta(1/fps);elapsed+=dt;s.step(1,dt);}
  assert.ok(Math.abs(elapsed-2)<1e-9);assert.ok(Math.abs(s.value-1)<.001);
 }
 assert.equal(frameDelta(-1),0);assert.equal(frameDelta(NaN),0);assert.ok(frameDelta(60)<=1.05);
});
