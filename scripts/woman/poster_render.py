import bpy, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
stage = argv[0] if argv else 'preview'
out = argv[1] if len(argv) > 1 else f'/home/roland/ai3d/projects/woman01/renders/poster_char_{stage}.png'
frame = int(argv[2]) if len(argv) > 2 else 20

PROJECT = '/home/roland/ai3d/projects/woman01'
bpy.ops.wm.open_mainfile(filepath=f'{PROJECT}/dress.blend')
scene = bpy.context.scene
arm = bpy.data.objects['CharacterArmature']

# Bring in the Wave animation from the source asset, then delete its duplicate rig.
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=f'{PROJECT}/refs/models/anim3.glb')
new_objects = [o for o in bpy.data.objects if o not in before]
wave = next(a for a in bpy.data.actions if 'Wave' in a.name)
for o in new_objects:
    bpy.data.objects.remove(o, do_unlink=True)
if not arm.animation_data:
    arm.animation_data_create()
arm.animation_data.action = wave
scene.frame_set(frame)
# Freeze the evaluated wave pose: remove the action so mesh edits and extra
# bone rotations below survive the final render evaluation.
for pb in arm.pose.bones:
    pb.rotation_mode = 'QUATERNION'
bpy.context.view_layer.update()
arm.animation_data.action = None
bpy.context.view_layer.update()

# --- wind: flare the lower skirt, sweep the long hair to her left ---
legs = bpy.data.objects['Formal_Legs']
me = legs.data
mat_idx = next(i for i, m in enumerate(me.materials) if m and m.name == 'LimeGreen')
skirt_ids = set()
for poly in me.polygons:
    if poly.material_index == mat_idx:
        skirt_ids.update(poly.vertices)
ys = [me.vertices[i].co.y for i in skirt_ids]
y_top, y_bot = max(ys), min(ys)
for i in skirt_ids:
    co = me.vertices[i].co
    t = max(0.0, min(1.0, (co.y - y_top) / (y_bot - y_top)))
    if t <= 0:
        continue
    # +X is the direction of the wind in this rig's local space.
    co.x += (0.00095 * t ** 1.75) + (0.00016 * t * t * math.sin(co.z * 1250 + t * 5.0))
    co.z += 0.00030 * t ** 1.5 * math.sin(t * 2.6 + 0.7) + 0.00008 * t * math.sin(co.z * 900 + 2.1)
    co.y -= 0.00013 * t ** 2.2  # tiny lift at the hem

hair = bpy.data.objects['LongHair']
hme = hair.data
hy = [v.co.y for v in hme.vertices]
hy_top, hy_bot = max(hy), min(hy)
for v in hme.vertices:
    co = v.co
    t = max(0.0, min(1.0, (co.y - hy_top) / (hy_bot - hy_top)))
    if t <= 0.02:
        continue
    co.x += 0.00080 * t ** 1.8 + 0.00010 * t ** 2 * math.sin(co.y * 900 + 1.3)
    co.z += 0.00040 * t ** 1.6 + 0.00006 * t * math.sin(t * 8.0)
    co.y -= 0.00008 * t ** 2
legs.data.update()
hair.data.update()

# --- studio lighting, tuned for a bright blue-sky composite ---
world = bpy.data.worlds.new('SkyLight')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs[0].default_value = (0.43, 0.63, 0.82, 1.0)
bg.inputs[1].default_value = 0.55

def add_area(name, loc, energy, size, color, target=(0, 0, 1.05)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = energy
    ld.shape = 'DISK'
    ld.size = size
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob

add_area('Key', (-2.4, -3.0, 3.0), 120, 2.4, (1.0, 0.95, 0.87))
add_area('Fill', (2.6, -2.6, 1.5), 48, 3.0, (0.72, 0.84, 1.0))
add_area('Rim-Warm', (2.1, 2.2, 3.1), 150, 1.5, (1.0, 0.86, 0.65), target=(0, 0, 1.25))
add_area('Rim-Cool', (-2.1, 2.4, 2.2), 70, 1.8, (0.75, 0.87, 1.0), target=(0, 0, 1.1))
add_area('Top', (0.0, -0.3, 4.2), 35, 2.0, (1.0, 0.98, 0.92))

# --- camera: 9:16 portrait, 85mm, a gentle 3/4 angle ---
cam_data = bpy.data.cameras.new('PosterCam')
cam = bpy.data.objects.new('PosterCam', cam_data)
scene.collection.objects.link(cam)
az = math.radians(17)
dist = 6.2
target = Vector((0, 0, 0.96))
cam.location = (math.sin(az) * dist, -math.cos(az) * dist, 1.30)
cam_data.lens = 85
cam_data.sensor_width = 36
cam_data.dof.use_dof = True
cam_data.dof.focus_distance = dist
cam_data.dof.aperture_fstop = 5.6
cam.rotation_euler = (target - Vector(cam.location)).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam

# --- render settings ---
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 24 if stage == 'preview' else 56
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.film_transparent = True
scene.render.resolution_x = 810 if stage == 'preview' else 2160
scene.render.resolution_y = 1440 if stage == 'preview' else 3840
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.2
scene.render.filepath = out
# save the working scene for later tweaks (before rendering changes nothing)
bpy.ops.wm.save_as_mainfile(filepath=f'{PROJECT}/poster.blend')
bpy.ops.render.render(write_still=True)
print('WROTE', out)
