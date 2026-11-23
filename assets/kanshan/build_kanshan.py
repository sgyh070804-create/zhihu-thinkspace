import bmesh, bpy, math, json, pathlib
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT;OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
model=bpy.data.collections.new('KANSHAN_Model');scene.collection.children.link(model)
cage=bpy.data.collections.new('EDITABLE_Control_Cages');scene.collection.children.link(cage);cage.hide_render=True;cage.hide_viewport=True
def put(obj,col):
 for c in list(obj.users_collection):c.objects.unlink(obj)
 col.objects.link(obj)
def mat(name,color,rough=.5,grain=False):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 n=m.node_tree.nodes;p=n.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough
 if grain:
  tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=165;tex.inputs['Detail'].default_value=2
  bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.10;bump.inputs['Distance'].default_value=.009
  m.node_tree.links.new(tex.outputs['Fac'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal'])
 return m
white=mat('Warm white - fine matte polymer',(.91,.905,.89),.64,True)
black=mat('Black limbs - soft rubber',(.012,.014,.015),.58,True)
nosemat=mat('Black muzzle tip - satin',(.009,.010,.011),.54,True)
eyemat=mat('Tiny black eyes',(.007,.008,.009),.25)
def mesh(name,verts,faces,material,col=model):
 data=bpy.data.meshes.new(name+'_Mesh');data.from_pydata(verts,[],faces);data.update()
 o=bpy.data.objects.new(name,data);col.objects.link(o);o.data.materials.append(material)
 for p in data.polygons:p.use_smooth=True
 return o
def active(o):
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
def apply(o,mod):active(o);bpy.ops.object.modifier_apply(modifier=mod.name)
def savecage(o):
 c=o.copy();c.data=o.data.copy();c.name='CAGE_'+o.name;cage.objects.link(c);c.hide_render=True
def weld(objects,name,voxel=.018):
 for o in objects:savecage(o)
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join();o=objects[0];o.name=name
 mod=o.modifiers.new('Weld continuous surface','REMESH');mod.mode='VOXEL';mod.voxel_size=voxel;mod.use_smooth_shade=True;apply(o,mod)
 mod=o.modifiers.new('Relax surface transitions','SMOOTH');mod.factor=.75;mod.iterations=35 if name=='Kanshan_White_Continuous_Surface' else 8;apply(o,mod)
 mod=o.modifiers.new('Surface subdivision','SUBSURF');mod.levels=1;mod.render_levels=1
 return o
def interp(points,x):
 # Monotone cubic Hermite slopes: C1 continuity without flat bands at each section.
 n=len(points)
 if x<=points[0][0]:return points[0][1:]
 if x>=points[-1][0]:return points[-1][1:]
 i=next(k for k in range(n-1) if points[k][0]<=x<=points[k+1][0])
 h=points[i+1][0]-points[i][0];t=(x-points[i][0])/h;out=[]
 for j in range(1,len(points[0])):
  hs=[points[k+1][0]-points[k][0] for k in range(n-1)]
  d=[(points[k+1][j]-points[k][j])/hs[k] for k in range(n-1)]
  slopes=[d[0]]
  for k in range(1,n-1):
   if d[k-1]*d[k]<=0:slopes.append(0)
   else:
    w1=2*hs[k]+hs[k-1];w2=hs[k]+2*hs[k-1]
    slopes.append((w1+w2)/(w1/d[k-1]+w2/d[k]))
  slopes.append(d[-1])
  out.append((2*t**3-3*t**2+1)*points[i][j]+(t**3-2*t**2+t)*h*slopes[i]+(-2*t**3+3*t**2)*points[i+1][j]+(t**3-t**2)*h*slopes[i+1])
 return out
def closed_rings(name,rings,material):
 n=len(rings[0]);v=[p for ring in rings for p in ring];f=[]
 for k in range(len(rings)-1):
  for i in range(n):f.append((k*n+i,k*n+(i+1)%n,(k+1)*n+(i+1)%n,(k+1)*n+i))
 f.append(tuple(reversed(range(n))));f.append(tuple((len(rings)-1)*n+i for i in range(n)))
 o=mesh(name,v,f,material)
 # Recalculate outward normals for consistent remeshing and export.
 active(o);bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.normals_make_consistent(inside=False);bpy.ops.object.mode_set(mode='OBJECT')
 return o
def organic(name,center,scale,material,power=2,segments=64,rows=32):
 rings=[]
 for j in range(1,rows):
  phi=-math.pi/2+math.pi*j/rows;cp=math.cos(phi);zp=math.sin(phi)
  ring=[]
  for i in range(segments):
   t=2*math.pi*i/segments;c,s=math.cos(t),math.sin(t)
   sign=lambda q: math.copysign(abs(q)**(2/power),q)
   ring.append((center[0]+scale[0]*cp*sign(c),center[1]+scale[1]*cp*sign(s),center[2]+scale[2]*zp))
  rings.append(ring)
 rings.insert(0,[(center[0]+.0001*math.cos(i*2*math.pi/segments),center[1]+.0001*math.sin(i*2*math.pi/segments),center[2]-scale[2]) for i in range(segments)])
 rings.append([(center[0]+.0001*math.cos(i*2*math.pi/segments),center[1]+.0001*math.sin(i*2*math.pi/segments),center[2]+scale[2]) for i in range(segments)])
 return closed_rings(name,rings,material)

# Cross-sections measured against the supplied front/profile/back reference.
# z, half width, front depth, back depth, local muzzle extension.
profile=[
 (.79,.05,-.02,.02,0),(.83,.35,-.29,.29,0),(.91,.65,-.48,.48,0),(1.05,.83,-.63,.64,0),
 (1.28,.94,-.74,.76,0),(1.65,.96,-.75,.85,0),(2.0,.93,-.69,.87,0),(2.30,.90,-.65,.84,.02),
 (2.42,.90,-.65,.83,.14),(2.55,.89,-.65,.81,.39),(2.69,.88,-.67,.78,.61),
 (2.86,.87,-.69,.75,.80),(3.04,.85,-.71,.72,.90),(3.16,.84,-.73,.70,.87),
 (3.25,.82,-.72,.67,.80),(3.30,.80,-.71,.65,.66),(3.34,.78,-.69,.64,.45),
 (3.37,.75,-.62,.60,.18),(3.43,.64,-.46,.48,.06),(3.47,.30,-.20,.23,0),(3.48,.03,-.02,.02,0),
]
rings=[]
for j in range(145):
 z=.79+(3.48-.79)*j/144;rx,front,back,muzzle=interp(profile,z);ring=[]
 for i in range(128):
  t=math.pi*2*i/128;cx,sy=math.cos(t),math.sin(t)
  exponent=2/2.35
  x=rx*math.copysign(abs(cx)**exponent,cx)
  y=(back if sy>=0 else -front)*math.copysign(abs(sy)**exponent,sy)
  y-=muzzle*max(0,-sy)**8
  ring.append((x,y,z))
 rings.append(ring)
body=closed_rings('Body_head_continuous_loft',rings,white)
ears=[]
for side in [-1,1]:
 ep=[(3.16,.32,.35),(3.34,.30,.33),(3.52,.25,.27),(3.68,.18,.20),(3.79,.10,.12),(3.83,.035,.05),(3.84,.005,.008)]
 er=[]
 for j in range(41):
  z=3.16+.68*j/40;rx,ry=interp(ep,z);cx=side*(.51+.055*(z-3.16)/.68)
  er.append([(cx+rx*math.cos(i*2*math.pi/64),.24+ry*math.sin(i*2*math.pi/64),z) for i in range(64)])
 ears.append(closed_rings('Ear_'+str(side)+'_loft',er,white))
tail=organic('Short_round_tail',(0,.91,1.35),(.32,.40,.33),white)
body=weld([body,*ears,tail],'Kanshan_White_Continuous_Surface',.018)
# Split faces at the color boundary while keeping the muzzle one connected surface.
body.data.materials.append(nosemat)
cut_origin = Vector((0, -1.19, 2.94))
cut_normal = Vector((0, 1, -.10)).normalized()
surface = bmesh.new()
surface.from_mesh(body.data)
bmesh.ops.bisect_plane(
 surface, geom=[*surface.verts, *surface.edges, *surface.faces], dist=1e-6,
 plane_co=cut_origin, plane_no=cut_normal,
)
for face in surface.faces:
 if (face.calc_center_median() - cut_origin).dot(cut_normal) < 0:
  face.material_index = 1
surface.to_mesh(body.data)
surface.free()
body.data.update()
eyes=[]
for side in [-1,1]:
 eye=organic('Eye_'+('L' if side<0 else 'R'),(side*.645,-.57,2.96),(.052,.042,.083),eyemat,2,32,20)
 eyes.append(eye)

def tube(name,points,material,segments=20,steps=48):
 # Spline centerline with explicit radial cross-sections, not capsule primitives.
 rings=[]
 from mathutils import geometry
 for j in range(steps+1):
  u=j/steps*(len(points)-1);idx=min(int(u),len(points)-2);t=u-idx
  p0=Vector(points[max(0,idx-1)][:3]);p1=Vector(points[idx][:3]);p2=Vector(points[idx+1][:3]);p3=Vector(points[min(len(points)-1,idx+2)][:3])
  def cat(v):return .5*((2*p1)+(-p0+p2)*v+(2*p0-5*p1+4*p2-p3)*v*v+(-p0+3*p1-3*p2+p3)*v*v*v)
  p=cat(t);q=cat(min(1,t+.003)) if t<.997 else p2;direction=q-p
  if direction.length<1e-5:direction=p2-p1
  direction.normalize();ref=Vector((0,1,0));n=direction.cross(ref).normalized();b=direction.cross(n).normalized()
  r=points[idx][3]*(1-t)+points[idx+1][3]*t
  rings.append([tuple(p+r*(math.cos(i*2*math.pi/segments)*n+math.sin(i*2*math.pi/segments)*b)) for i in range(segments)])
 return closed_rings(name,rings,material)
arms=[];legs=[]
for side in [-1,1]:
 points=[(side*.84,.02,2.17,.035),(side*.94,-.015,2.07,.095),(side*1.035,-.045,1.82,.105),(side*1.09,-.10,1.55,.106),(side*1.10,-.16,1.31,.11),(side*1.09,-.19,1.20,.10)]
 arm=tube('Arm_'+str(side)+'_spline',points,black)
 palm=organic('Palm_'+str(side),(side*1.10,-.19,1.18),(.13,.105,.17),black)
 fingers=[]
 for k in [-1,0,1]:
  x=side*(1.10+k*.076);base=1.19;end=.985+(abs(k)*.025)
  fingers.append(tube('Finger_'+str(side)+'_'+str(k),[(x,-.21,base,.054),(x+side*.006,-.225,1.07,.052),(x+side*.012,-.24,end,.038),(x+side*.013,-.24,end-.02,.007)],black,14,20))
 fingers.append(tube('Thumb_'+str(side),[(side*1.02,-.21,1.26,.065),(side*.956,-.245,1.18,.056),(side*.94,-.26,1.13,.025)],black,16,24))
 arm=weld([arm,palm,*fingers],'Kanshan_Arm_'+('L' if side<0 else 'R'),.010);arms.append(arm)
 leg=tube('Leg_'+str(side),[(side*.37,.02,.88,.13),(side*.37,.015,.55,.145),(side*.37,-.005,.22,.15),(side*.37,-.015,.13,.13)],black,24,30)
 foot=organic('Foot_'+str(side),(side*.37,-.15,.14),(.215,.31,.14),black,2.8)
 legs.append(weld([leg,foot],'Kanshan_Leg_'+('L' if side<0 else 'R'),.012))

# A real deform armature: arm meshes blend upper/lower arm influences.
armdata=bpy.data.armatures.new('Kanshan_Skeleton');rig=bpy.data.objects.new('Kanshan_Rig',armdata);model.objects.link(rig);active(rig);bpy.ops.object.mode_set(mode='EDIT')
def bone(name,h,t,parent=None):
 b=armdata.edit_bones.new(name);b.head=h;b.tail=t
 if parent:b.parent=armdata.edit_bones[parent]
 return b
bone('root',(0,0,.08),(0,0,.80));bone('body',(0,0,.80),(0,0,2.14),'root');bone('head',(0,0,2.14),(0,0,3.45),'body')
for side,label in [(-1,'L'),(1,'R')]:
 bone('upper_arm.'+label,(side*.86,0,2.15),(side*1.07,-.08,1.65),'body')
 bone('forearm.'+label,(side*1.07,-.08,1.65),(side*1.10,-.18,1.25),'upper_arm.'+label)
 bone('hand.'+label,(side*1.10,-.18,1.25),(side*1.10,-.22,1.02),'forearm.'+label)
 bone('leg.'+label,(side*.37,0,.85),(side*.37,0,.14),'root')
bpy.ops.object.mode_set(mode='OBJECT');rig.show_in_front=True
def bind(o,weights):
 for name,values in weights.items():
  g=o.vertex_groups.new(name=name)
  for idx,w in values:
   if w>.0001:g.add([idx],w,'REPLACE')
 mod=o.modifiers.new('Kanshan skeletal deformation','ARMATURE');mod.object=rig;o.parent=rig
weights={'body':[],'head':[]}
for v in body.data.vertices:
 t=max(0,min(1,(v.co.z-2.15)/.65))
 if v.co.z > 2.30:
  t=max(t,min(1,(-v.co.y-.80)/.28))
 weights['head'].append((v.index,t));weights['body'].append((v.index,1-t))
bind(body,weights)
for o in eyes:bind(o,{'head':[(v.index,1) for v in o.data.vertices]})
for i,o in enumerate(arms):
 label='L' if i==0 else 'R';w={k+'.'+label:[] for k in ['upper_arm','forearm','hand']}
 for v in o.data.vertices:
  z=v.co.z;upper=max(0,min(1,(z-1.50)/.28));handweight=max(0,min(1,(1.40-z)/.20));fore=max(0,1-upper-handweight)
  for k,value in [('upper_arm',upper),('forearm',fore),('hand',handweight)]:w[k+'.'+label].append((v.index,value))
 bind(o,w)
for i,o in enumerate(legs):bind(o,{'leg.'+('L' if i==0 else 'R'):[(v.index,1) for v in o.data.vertices]})

# Pack the supplied reference as source data inside the editable file.
refpath=ROOT/'references/three-view.jpg'
image=bpy.data.images.load(str(refpath));image.pack();image.filepath='//references/three-view.jpg'
rig['reference']='User supplied kanshan_material.zip / original front-side-back JPG'
rig['modeling_method']='Reference-proportioned cross-section lofts; welded ears/tail; spline arms with fused fingers; deform armature'
rig['status']='Reference reconstruction; not the original official production mesh'

# Studio, orthographic cameras and neutral white balance.
ground=mat('Studio floor',(.44,.44,.45),.8)
bpy.ops.mesh.primitive_plane_add(size=200);floor=bpy.context.object;floor.name='Studio_Floor';floor.data.materials.append(ground)
world=bpy.data.worlds.new('Studio World');scene.world=world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.5,.5,.5,1);world.node_tree.nodes['Background'].inputs[1].default_value=.35
def area(name,location,power,size):
 d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=location;o.rotation_euler=(Vector((0,0,2))-o.location).to_track_quat('-Z','Y').to_euler()
area('Large softbox',(-4,-6,8),700,5);area('Fill',(5,-3,5),400,4);area('Rim',(1,5,7),600,4)
def camera(name,loc,target=(0,0,1.95),scale=4.55):
 d=bpy.data.cameras.new(name);o=bpy.data.objects.new(name,d);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler();d.type='ORTHO';d.ortho_scale=scale;return o
cameras=[camera('Front',(0,-10,1.95)),camera('Side',(10,0,1.95)),camera('Back',(0,10,1.95)),camera('Hero',(6,-9,4.6),scale=4.9)]
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.resolution_x=900;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
scene.camera=cameras[3]
# Save editable, packed project before render/export.
scene.render.filepath='//renders/'
bpy.context.preferences.filepaths.save_version=0
active(rig);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'kanshan-source.blend'),compress=True)
print('BLEND_SAVED',flush=True)
# Export only the actual model, excluding studio and control cages.
bpy.ops.object.select_all(action='DESELECT')
for o in model.objects:o.select_set(True)
bpy.context.view_layer.objects.active=rig
bpy.ops.export_scene.gltf(filepath=str(OUT/'kanshan-reference-model.glb'),export_format='GLB',use_selection=True,export_apply=False,export_animations=False)
print('GLB_EXPORTED',flush=True)
stats={}
for o in model.objects:
 if o.type=='MESH':
  bm=bmesh.new();bm.from_mesh(o.data);stats[o.name]={'vertices':len(o.data.vertices),'faces':len(o.data.polygons),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges)};bm.free()
(OUT/'mesh-validation.json').write_text(json.dumps({'blender':bpy.app.version_string,'meshes':stats,'bones':len(armdata.bones),'source':'supplied three-view reference','scale':'stylized reference height 3.84 Blender units'},indent=2),encoding='utf8')
for cam in cameras:
 scene.camera=cam;scene.render.filepath=str(OUT/('render-'+cam.name.lower()+'.png'));bpy.ops.render.render(write_still=True);print('RENDERED',cam.name,flush=True)
print('ALL_DONE',flush=True)
