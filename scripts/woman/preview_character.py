import bpy, sys, os, math
from mathutils import Vector

argv=sys.argv[sys.argv.index('--')+1:]
path, out = argv[0], argv[1]
action_name = argv[2] if len(argv)>2 else ''
frame = int(argv[3]) if len(argv)>3 else 1
angle_deg = float(argv[4]) if len(argv)>4 else 25.0

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
for o in list(bpy.context.scene.objects):
    if o.type=='MESH' and o.name.startswith('Icosphere'):
        bpy.data.objects.remove(o, do_unlink=True)

# normalize to 1.72 m
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
lo=Vector((1e9,1e9,1e9)); hi=Vector((-1e9,-1e9,-1e9))
for o in meshes:
    for v in o.data.vertices:
        w=o.matrix_world @ v.co
        lo=Vector((min(lo[i],w[i]) for i in range(3))); hi=Vector((max(hi[i],w[i]) for i in range(3)))
h=hi.z-lo.z
scale=1.72/h
root=bpy.data.objects.get('RootNode')
if root:
    root.scale = tuple(s*scale for s in root.scale)
    # after scale, drop to floor: recompute
    bpy.context.view_layer.update()
lo=Vector((1e9,1e9,1e9)); hi=Vector((-1e9,-1e9,-1e9))
for o in meshes:
    for v in o.data.vertices:
        w=o.matrix_world @ v.co
        lo=Vector((min(lo[i],w[i]) for i in range(3))); hi=Vector((max(hi[i],w[i]) for i in range(3)))
if root:
    root.location.z -= lo.z
bpy.context.view_layer.update()

# pose action
arm=bpy.data.objects.get('HumanArmature')
if arm:
    arm.data.pose_position='POSE'
    if action_name:
        act=bpy.data.actions.get(action_name)
        if not act:
            cands=[a for a in bpy.data.actions if a.name.startswith(action_name)]
            act=cands[0] if cands else None
        if act:
            if not arm.animation_data: arm.animation_data_create()
            arm.animation_data.action=act
            # action slots Blender 4.2
            try:
                arm.animation_data.action_slot = act.slots[0]
            except Exception: pass
            bpy.context.scene.frame_set(frame)
            print('ACTION', act.name, 'frame', frame)
        else:
            print('ACTION NOT FOUND', action_name, '; have', [a.name for a in bpy.data.actions][:20])
    # shade smooth
    for o in meshes:
        for p in o.data.polygons: p.use_smooth=True
        try: o.data.shade_smooth_by_angle = math.radians(35)
        except Exception: pass

# recalc bounds
lo=Vector((1e9,1e9,1e9)); hi=Vector((-1e9,-1e9,-1e9))
for o in meshes:
    for v in o.data.vertices:
        w=o.matrix_world @ v.co
        lo=Vector((min(lo[i],w[i]) for i in range(3))); hi=Vector((max(hi[i],w[i]) for i in range(3)))
print('BOUNDS', tuple(round(v,3) for v in lo), tuple(round(v,3) for v in hi))
print('MATS', [(m.name, tuple(round(x,3) for x in m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value)) for m in bpy.data.materials if m.use_nodes and m.node_tree.nodes.get('Principled BSDF')])

# palette for preview: white dress, warm skin, dark hair
palette={'Dress':(0.55,0.53,0.49,1),'Skin':(0.38,0.21,0.13,1),'Shoes':(0.65,0.62,0.56,1),'Hair':(0.035,0.018,0.014,1),'HairBase':(0.05,0.03,0.02,1),'Eyes':(0.01,0.008,0.006,1)}
for m in bpy.data.materials:
    if m.name in palette and m.use_nodes:
        b=m.node_tree.nodes.get('Principled BSDF')
        if b:
            b.inputs['Base Color'].default_value=palette[m.name]
            b.inputs['Metallic'].default_value=0.0
            b.inputs['Roughness'].default_value=0.62 if m.name!='Eyes' else 0.18

# world
w=bpy.data.worlds.new('W'); bpy.context.scene.world=w; w.use_nodes=True
nt=w.node_tree; bg=nt.nodes['Background']
sky=nt.nodes.new('ShaderNodeTexSky'); sky.sky_type='NISHITA'; sky.sun_elevation=math.radians(35); sky.sun_rotation=math.radians(140)
nt.links.new(sky.outputs[0],bg.inputs[0]); bg.inputs[1].default_value=0.12
# floor
bpy.ops.mesh.primitive_plane_add(size=30, location=(0,0,0))
floor=bpy.context.object
fm=bpy.data.materials.new('Floor'); fm.use_nodes=True
fb=fm.node_tree.nodes['Principled BSDF']
fb.inputs['Base Color'].default_value=(0.12,0.16,0.22,1); fb.inputs['Roughness'].default_value=0.75
floor.data.materials.append(fm)
# camera
cam_data=bpy.data.cameras.new('Cam'); cam=bpy.data.objects.new('Cam',cam_data); bpy.context.scene.collection.objects.link(cam)
target=Vector((0,0,0.92))
a=math.radians(angle_deg)
cam.location=(math.sin(a)*3.7, -math.cos(a)*3.7, 1.60)
cam_data.lens=72
d=target-cam.location; cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
bpy.context.scene.camera=cam
# lights
def area(loc, energy, size, color):
    ld=bpy.data.lights.new('L','AREA'); ld.energy=energy; ld.size=size; ld.color=color
    ob=bpy.data.objects.new('L',ld); bpy.context.scene.collection.objects.link(ob); ob.location=loc
    dd=target-Vector(loc); ob.rotation_euler=dd.to_track_quat('-Z','Y').to_euler()
    return ob
area((-2.2,-2.8,3.2), 28, 2.5, (1.0,0.94,0.86))
area((2.8,-1.2,2.2), 9, 2.0, (0.72,0.83,1.0))
area((0.5,3.0,2.8), 22, 2.0, (1.0,0.86,0.66))
area((0,-2.5,1.0), 3, 1.2, (1.0,0.97,0.9))
sc=bpy.context.scene
sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=48; sc.cycles.use_denoising=True
sc.render.resolution_x=760; sc.render.resolution_y=980; sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG'; sc.render.filepath=out
sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'
sc.view_settings.exposure=-0.7
bpy.ops.render.render(write_still=True)
print('WROTE',out)
