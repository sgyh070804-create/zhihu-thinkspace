import bpy,pathlib,json
R=pathlib.Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(R/'kanshan-source.blend'))
source=R

collection=bpy.data.collections['KANSHAN_Model'];total=0
for o in collection.objects:
 if o.type!='MESH':continue
 bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 for m in list(o.modifiers):
  if m.type=='SUBSURF':o.modifiers.remove(m)
 if len(o.data.polygons)>3000:
  dec=o.modifiers.new('Runtime LOD - preserve silhouette','DECIMATE');dec.ratio=.30;dec.use_collapse_triangulate=True
  # Apply before skinning so vertex weights remain attached to the reduced mesh.
  bpy.ops.object.modifier_move_up(modifier=dec.name)
  bpy.ops.object.modifier_apply(modifier=dec.name)
 total+=len(o.data.polygons)
bpy.ops.object.select_all(action='DESELECT')
for o in collection.objects:o.select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects['Kanshan_Rig']
target=R
bpy.ops.export_scene.gltf(filepath=str(target/'kanshan-runtime.glb'),export_format='GLB',use_selection=True,export_apply=False,export_animations=False)
print('RUNTIME_FACES',total,flush=True)
