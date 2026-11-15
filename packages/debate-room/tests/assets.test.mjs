import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const bytes=readFileSync(new URL('../assets/kanshan/kanshan-runtime.glb',import.meta.url));
const jsonLength=bytes.readUInt32LE(12),gltf=JSON.parse(bytes.subarray(20,20+jsonLength)),binaryStart=28+jsonLength;
test('packaged Kanshan is a self-contained skinned GLB',()=>{
 assert.equal(bytes.toString('ascii',0,4),'glTF');assert.equal(bytes.readUInt32LE(4),2);assert.equal(bytes.readUInt32LE(8),bytes.length);
 assert.equal(gltf.meshes.length,8);assert.equal(gltf.skins[0].joints.length,11);
 assert.ok(gltf.buffers.every(b=>!b.uri));
 const bones=new Set(gltf.skins[0].joints.map(i=>gltf.nodes[i].name));
 for(const name of ['head','body','upper_arm.L','forearm.R','hand.R','leg.L'])assert.ok(bones.has(name),name);
});
test('runtime skin weights are finite, normalized and use valid joints',()=>{
 const componentBytes={5121:1,5123:2,5126:4};
 function value(index,row,column){const a=gltf.accessors[index],b=gltf.bufferViews[a.bufferView],size=componentBytes[a.componentType];assert.ok(size);const offset=binaryStart+(b.byteOffset||0)+(a.byteOffset||0)+row*(b.byteStride||size*4)+column*size;return a.componentType===5126?bytes.readFloatLE(offset):a.componentType===5123?bytes.readUInt16LE(offset):bytes.readUInt8(offset);}
 let vertices=0;
 for(const mesh of gltf.meshes)for(const p of mesh.primitives){
  const weights=p.attributes.WEIGHTS_0,joints=p.attributes.JOINTS_0;assert.notEqual(weights,undefined);assert.notEqual(joints,undefined);
  for(let row=0;row<gltf.accessors[weights].count;row++){
   let sum=0;for(let k=0;k<4;k++){const w=value(weights,row,k),joint=value(joints,row,k);assert.ok(Number.isFinite(w)&&w>=0&&w<=1);assert.ok(joint<11);sum+=w;}assert.ok(Math.abs(sum-1)<.001,`weight sum ${sum}`);vertices++;
  }
 }
 assert.ok(vertices>10000);
});
