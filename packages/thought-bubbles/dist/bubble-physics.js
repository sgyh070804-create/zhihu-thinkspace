(function(global){
  'use strict';
  const N=64, TAU=Math.PI*2, directions=Array.from({length:N},(_,i)=>[Math.cos(i*TAU/N),Math.sin(i*TAU/N)]);
  function ensure(b){if(!b.membrane)b.membrane={offset:new Float32Array(N),velocity:new Float32Array(N),force:new Float32Array(N)};return b.membrane;}
  function radiusAt(b,angle){const m=ensure(b),u=((angle/TAU)%1+1)%1*N,i=Math.floor(u),f=u-i;return b.r*(1+m.offset[i]*(1-f)+m.offset[(i+1)%N]*f);}
  function gap(a,b){const theta=Math.atan2(b.y-a.y,b.x-a.x);return Math.hypot(b.x-a.x,b.y-a.y)-radiusAt(a,theta)-radiusAt(b,theta+Math.PI);}
  function capture(a,b,previous=false){const tolerance=Math.max(1,Math.min(3,Math.min(a.r,b.r)*.015));return gap(a,b)<=tolerance+(previous?3:0);}
  function solve(bodies,dt,bounds,mergedPair){
    const steps=Math.max(1,Math.ceil(dt*240)),h=dt/steps,baseArea=N*Math.sin(TAU/N)*.5;
    bodies.forEach(ensure);
    for(let step=0;step<steps;step++){
      for(const b of bodies){const m=b.membrane,u=m.offset,v=m.velocity,f=m.force;let area=0;
        for(let j=0;j<N;j++)area+=(1+u[j])*(1+u[(j+1)%N])*Math.sin(TAU/N)*.5;
        const pressure=(baseArea-area)/baseArea*130;
        for(let j=0;j<N;j++){
          // Discrete membrane tension, enclosed-area pressure, and viscous damping.
          f[j]=-65*u[j]+190*(u[(j+N-1)%N]+u[(j+1)%N]-2*u[j])+pressure-9*v[j];
          const dir=directions[j],length=b.r*(1+u[j]),px=b.x+dir[0]*length,py=b.y+dir[1]*length;
          for(const other of bodies){if(other===b)continue;if(mergedPair&&mergedPair.includes(b)&&mergedPair.includes(other))continue;
            if(Math.hypot(b.x-other.x,b.y-other.y)>1.5*(b.r+other.r))continue;
            const dx=px-other.x,dy=py-other.y,d=Math.hypot(dx,dy)||.001,normal=(dx*dir[0]+dy*dir[1])/d;
            const penetration=radiusAt(other,Math.atan2(dy,dx))-d;
            if(penetration>0&&normal<0)f[j]+=Math.max(-160,penetration/b.r*normal*480);
          }
          if(bounds){const penetration=Math.max(0,-px,px-bounds.width,-py,py-bounds.height);if(penetration>0)f[j]-=penetration/b.r*350;}
        }
      }
      // Simultaneous update keeps pair order from biasing the collision.
      for(const b of bodies){const m=b.membrane;for(let j=0;j<N;j++){m.velocity[j]+=m.force[j]*h;m.offset[j]=Math.max(-.38,Math.min(.30,m.offset[j]+m.velocity[j]*h));}}
    }
  }
  function impulse(b,amount=.07,angle=0){const m=ensure(b);for(let j=0;j<N;j++)m.velocity[j]+=amount*Math.cos(2*(j*TAU/N-angle));}
  const api={N,ensure,radiusAt,gap,capture,solve,impulse};global.BubblePhysics=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
