import bpy,sys,math
from mathutils import Vector
argv=sys.argv[sys.argv.index('--')+1:]
path,out,prefix=argv[0],argv[1],argv[2]
angle=float(argv[3]) if len(argv)>3 else 22
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
for o in list(bpy.context.scene.objects):
    if o.type=='MESH' and o.name.startswith('Icosphere'): bpy.data.objects.remove(o,do_unlink=True)
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
for m in meshes:
    m.hide_render = not m.name.startswith(prefix)
    m.hide_set(not m.name.startswith(prefix))
for arm in arms:
    if not arm.animation_data: arm.animation_data_create()
    act=bpy.data.actions.get('Idle') or next((a for a in bpy.data.actions if 'Idle' in a.name),None)
    if act:
        arm.animation_data.action=act
        try:
            if hasattr(act,'slots') and len(act.slots): arm.animation_data.action_slot=act.slots[0]
        except Exception as e: print('slot',e)
bpy.context.scene.frame_set(12)
# bounds of visible meshes
dg=bpy.context.evaluated_depsgraph_get(); lo=Vector((1e9,)*3); hi=Vector((-1e9,)*3)
for o in meshes:
    if not o.name.startswith(prefix): continue
    ev=o.evaluated_get(dg); me=ev.to_mesh()
    for v in me.vertices:
        w=ev.matrix_world @ v.co
        lo=Vector((min(lo[i],w[i]) for i in range(3))); hi=Vector((max(hi[i],w[i]) for i in range(3)))
    ev.to_mesh_clear()
print('BOUNDS',tuple(round(v,3) for v in lo),tuple(round(v,3) for v in hi),'H',round(hi.z-lo.z,3))
# floor at min z
bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,lo.z-0.002))
floor=bpy.context.object; fm=bpy.data.materials.new('Floor'); fm.use_nodes=True
fb=fm.node_tree.nodes['Principled BSDF']; fb.inputs['Base Color'].default_value=(0.22,0.26,0.32,1); fb.inputs['Roughness'].default_value=0.8
floor.data.materials.append(fm)
# world
w=bpy.data.worlds.new('W'); bpy.context.scene.world=w; w.use_nodes=True
w.node_tree.nodes['Background'].inputs[0].default_value=(0.16,0.24,0.36,1); w.node_tree.nodes['Background'].inputs[1].default_value=0.9
# camera
cam_data=bpy.data.cameras.new('Cam'); cam=bpy.data.objects.new('Cam',cam_data); bpy.context.scene.collection.objects.link(cam)
target=Vector((0,0,lo.z+(hi.z-lo.z)*0.52)); a=math.radians(angle)
cam.location=(math.sin(a)*3.4,-math.cos(a)*3.4,lo.z+1.45); cam_data.lens=75
cam.rotation_euler=(target-Vector(cam.location)).to_track_quat('-Z','Y').to_euler(); bpy.context.scene.camera=cam
def area(loc,energy,size,color):
    ld=bpy.data.lights.new('L','AREA'); ld.energy=energy; ld.size=size; ld.color=color
    ob=bpy.data.objects.new('L',ld); bpy.context.scene.collection.objects.link(ob); ob.location=loc
    ob.rotation_euler=(target-Vector(loc)).to_track_quat('-Z','Y').to_euler()
area((-2.0,-2.7,2.8),70,2.6,(1.0,0.95,0.88))
area((2.6,-1.4,2.1),26,2.0,(0.72,0.84,1.0))
area((0.7,2.6,2.7),40,1.8,(1.0,0.86,0.68))
area((0,-2.6,1.55),14,1.5,(1.0,0.97,0.92))
sc=bpy.context.scene; sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=48; sc.cycles.use_denoising=True
sc.render.resolution_x=760; sc.render.resolution_y=980; sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG'; sc.render.filepath=out
sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'; sc.view_settings.exposure=0.0
bpy.ops.render.render(write_still=True)
print('WROTE',out)
