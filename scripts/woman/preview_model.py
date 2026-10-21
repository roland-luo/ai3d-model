import bpy, sys, os, math
from mathutils import Vector

path = sys.argv[sys.argv.index('--')+1]
out = sys.argv[sys.argv.index('--')+2]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)

meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
for a in arms:
    a.data.pose_position='REST'
# bounds
lo=Vector((1e9,1e9,1e9)); hi=Vector((-1e9,-1e9,-1e9))
for o in meshes:
    for c in o.bound_box:
        w=o.matrix_world @ Vector(c)
        lo=Vector((min(lo[i],w[i]) for i in range(3)))
        hi=Vector((max(hi[i],w[i]) for i in range(3)))
print('BOUNDS', tuple(round(v,3) for v in lo), tuple(round(v,3) for v in hi))
print('OBJECTS', [(o.name,o.type,len(o.data.vertices) if o.type=='MESH' else '') for o in bpy.context.scene.objects])
for o in meshes:
    print('MESH',o.name,'materials',[m.name if m else None for m in o.data.materials], 'dims',tuple(round(v,3) for v in o.dimensions))
    for m in o.data.materials:
        if m and m.use_nodes:
            bs=[n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED']
            if bs:
                b=bs[0]
                print('   MAT',m.name,'base',tuple(round(x,3) for x in b.inputs['Base Color'].default_value),'metal',round(b.inputs['Metallic'].default_value,2),'rough',round(b.inputs['Roughness'].default_value,2))

# world
w=bpy.data.worlds.new('W'); bpy.context.scene.world=w; w.use_nodes=True
bg=w.node_tree.nodes['Background']; bg.inputs[0].default_value=(0.05,0.06,0.08,1); bg.inputs[1].default_value=0.6
# floor
bpy.ops.mesh.primitive_plane_add(size=20, location=(0,0,lo.z-0.001))
floor=bpy.context.object
fm=bpy.data.materials.new('Floor'); fm.use_nodes=True
fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(0.12,0.13,0.15,1)
fm.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=0.5
floor.data.materials.append(fm)
# camera
cam_data=bpy.data.cameras.new('Cam'); cam=bpy.data.objects.new('Cam',cam_data); bpy.context.scene.collection.objects.link(cam)
target=Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,lo.z+(hi.z-lo.z)*0.52))
cam.location=(target.x, target.y-2.6, target.z+0.12)
cam_data.lens=70
d=target-cam.location
cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
bpy.context.scene.camera=cam
# lights
def area(loc, energy, size, color):
    ld=bpy.data.lights.new('L','AREA'); ld.energy=energy; ld.size=size; ld.color=color
    ob=bpy.data.objects.new('L',ld); bpy.context.scene.collection.objects.link(ob); ob.location=loc
    dd=target-Vector(loc); ob.rotation_euler=dd.to_track_quat('-Z','Y').to_euler()
area((-2.5,-2.5,3.2), 550, 3.0, (1.0,0.95,0.9))
area((2.5,-1.5,2.0), 200, 2.5, (0.7,0.8,1.0))
area((0,2.8,2.5), 350, 2.0, (1.0,0.8,0.55))
# render
sc=bpy.context.scene
sc.render.engine='CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=32; sc.cycles.use_denoising=True
sc.render.resolution_x=720; sc.render.resolution_y=900; sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG'; sc.render.filepath=out
sc.view_settings.view_transform='AgX'; sc.view_settings.look='AgX - Medium High Contrast'
bpy.ops.render.render(write_still=True)
print('WROTE',out)
