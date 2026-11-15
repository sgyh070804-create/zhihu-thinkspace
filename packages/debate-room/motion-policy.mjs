// Production discussion uses a supported rest: hands hang beside the body.
// A speaking beat may lift them briefly; a held pose is reserved for preview.
export function settleDiscussionArms(pose,gesture,elapsed,speaking){
 const bodyOnly=['listen','think','nod','write','sip'].includes(gesture);
 const phase=(elapsed-.15)/1.65;
 const weight=speaking&&!bodyOnly&&phase>0&&phase<1?Math.sin(Math.PI*phase)**2:0;
 for(const channel of ['lsX','lsZ','leX','lwZ','rsX','rsZ','reX','rwZ'])pose[channel]*=weight;
 return pose;
}
