# Blender 4.5: smooth unisex mannequin for OpenHolter's posture figure.
# Coordinates are the app's body frame directly: x = body's right, y = head, z = chest (metres).
# Run: Blender -b --python scripts/blender/mannequin.py -- <out_dir>
# then copy <out_dir>/mannequin.json to openholter/static/. Renders preview-*.png for checking.
import base64, json, math, sys
import bpy
import numpy as np
from mathutils import Vector, Quaternion

OUT = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
col = bpy.context.collection
SEG = 40
THICK = 1.08  # overall girth; 1.0 was a little slender


def _cr(p0, p1, p2, p3, t):  # Catmull-Rom on tuples
    return tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t * t + (-a + 3 * b - 3 * c + d) * t ** 3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def loft(name, prof, axis=(0, -1, 0), u=(1, 0, 0), v=(0, 0, 1), sub=6):
    """prof: [(s, cu, cv, ru, rv)] along `axis` (s = distance), elliptic sections, rounded caps."""
    axis, u, v = Vector(axis), Vector(u), Vector(v)
    P = [prof[0]] + prof + [prof[-1]]
    rings = []
    for i in range(1, len(P) - 2):
        for k in range(sub):
            rings.append(_cr(P[i - 1], P[i], P[i + 1], P[i + 2], k / sub))
    rings.append(prof[-1])
    # caps: quarter circle shrinking towards both ends
    def cap(r, sign):
        out = []
        L = min(r[3], r[4]) * 0.9
        for k in range(1, 7):
            a = k / 7 * math.pi / 2
            out.append((r[0] + sign * L * math.sin(a), r[1], r[2], r[3] * math.cos(a), r[4] * math.cos(a)))
        return out
    rings = list(reversed(cap(rings[0], -1))) + rings + cap(rings[-1], 1)
    verts, faces = [], []
    for (s_, cu, cv, ru, rv) in rings:
        ru, rv = ru * THICK, rv * THICK
        c = axis * s_ + u * cu + v * cv
        for j in range(SEG):
            a = 2 * math.pi * j / SEG
            verts.append(c + u * (ru * math.cos(a)) + v * (rv * math.sin(a)))
    n = len(rings)
    for i in range(n - 1):
        for j in range(SEG):
            a, b = i * SEG + j, i * SEG + (j + 1) % SEG
            faces.append((a, b, b + SEG, a + SEG))
    first = len(verts); verts.append(axis * (rings[0][0] - 0.0) + u * rings[0][1] + v * rings[0][2])
    last = len(verts); verts.append(axis * rings[-1][0] + u * rings[-1][1] + v * rings[-1][2])
    for j in range(SEG):
        faces.append((first, (j + 1) % SEG, j))
        faces.append((last, (n - 1) * SEG + j, (n - 1) * SEG + (j + 1) % SEG))
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(x) for x in verts], [], faces); me.update()
    me.validate()
    o = bpy.data.objects.new(name, me); col.objects.link(o)
    # make normals point outwards whatever the winding
    import bmesh
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free()
    return o


def ellipsoid(name, c, r):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24, radius=1, location=c)
    o = bpy.context.active_object; o.name = name; o.scale = r
    bpy.ops.object.transform_apply(scale=True)
    return o


# torso along -y from the neck base down; s = -y. Unisex: no chest / hip sex characteristics.
# (s, cx, cz, half-width, half-depth)
loft("torso", [
    (-0.375, 0, -0.014, 0.065, 0.058),
    (-0.35, 0, -0.014, 0.115, 0.074),
    (-0.315, 0, -0.012, 0.185, 0.090),
    (-0.28, 0, -0.010, 0.205, 0.098),
    (-0.235, 0, -0.008, 0.196, 0.104),
    (-0.18, 0, -0.002, 0.172, 0.110),
    (-0.08, 0, 0.0, 0.160, 0.112),
    (0.04, 0, -0.002, 0.150, 0.104),
    (0.12, 0, -0.004, 0.142, 0.099),
    (0.24, 0, -0.006, 0.155, 0.103),
    (0.33, 0, -0.008, 0.166, 0.106),
    (0.39, 0, -0.012, 0.152, 0.096),
])
loft("neck", [(-0.50, 0, 0.0, 0.054, 0.054), (-0.43, 0, -0.008, 0.057, 0.056),
              (-0.36, 0, -0.016, 0.064, 0.060)])
ellipsoid("head", (0, 0.578, 0.012), (0.092, 0.116, 0.104))
ellipsoid("jaw", (0, 0.522, 0.042), (0.068, 0.054, 0.07))
ellipsoid("nose", (0, 0.574, 0.11), (0.014, 0.022, 0.016))
for sgn, side in ((1, "R"), (-1, "L")):
    x = sgn * 0.252
    loft("arm" + side, [
        (-0.275, x * 0.9, -0.012, 0.048, 0.052),
        (-0.24, x, -0.012, 0.054, 0.056),
        (-0.18, x, -0.012, 0.048, 0.050),
        (-0.06, x, -0.012, 0.042, 0.044),
        (0.04, x, -0.010, 0.038, 0.040),
        (0.10, x, -0.006, 0.039, 0.041),
        (0.19, x, -0.002, 0.032, 0.034),
        (0.265, x, 0.0, 0.022, 0.028),
    ])
    ellipsoid("hand" + side, (x, -0.335, 0.006), (0.023, 0.066, 0.045))
    x = sgn * 0.104
    loft("leg" + side, [
        (0.36, x, -0.004, 0.080, 0.082),
        (0.46, x, -0.002, 0.084, 0.086),
        (0.62, x, 0.0, 0.072, 0.074),
        (0.80, x, 0.004, 0.056, 0.058),
        (0.89, x, 0.008, 0.052, 0.054),
        (0.98, x, -0.004, 0.054, 0.058),
        (1.08, x, -0.004, 0.048, 0.050),
        (1.22, x, 0.0, 0.034, 0.034),
        (1.315, x, 0.0, 0.03, 0.03),
    ])
    # foot along +z (s = z), section in x-y
    loft("foot" + side, [
        (-0.045, x, -1.338, 0.034, 0.030),
        (0.02, x, -1.342, 0.040, 0.030),
        (0.09, x, -1.35, 0.043, 0.022),
        (0.135, x, -1.352, 0.036, 0.016),
    ], axis=(0, 0, 1), u=(1, 0, 0), v=(0, 1, 0))

# ---------------- fuse, smooth, reduce
bpy.ops.object.select_all(action="SELECT")
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = "mannequin"
m = body.modifiers.new("remesh", "REMESH"); m.mode = "VOXEL"; m.voxel_size = 0.005
bpy.ops.object.modifier_apply(modifier="remesh")
m = body.modifiers.new("smooth", "LAPLACIANSMOOTH"); m.lambda_factor = 0.5; m.iterations = 12
m.use_volume_preserve = True
bpy.ops.object.modifier_apply(modifier="smooth")
m = body.modifiers.new("dec", "DECIMATE"); m.ratio = 9000 / max(1, len(body.data.polygons))
bpy.ops.object.modifier_apply(modifier="dec")
m = body.modifiers.new("tri", "TRIANGULATE")
bpy.ops.object.modifier_apply(modifier="tri")
bpy.ops.object.shade_smooth()

# ---------------- armature for automatic (bone heat) weights; joints as in figure.js
JOINTS = {  # name: (head, tail, parent)
    "body": ((0, -0.46, 0), (0, 0.36, 0), None),
    "neck": ((0, 0.38, -0.01), (0, 0.72, 0.02), "body"),
}
for s, side in ((1, "R"), (-1, "L")):
    JOINTS["shoulder" + side] = ((s * 0.245, 0.27, -0.01), (s * 0.245, -0.04, -0.01), "body")
    JOINTS["elbow" + side] = ((s * 0.245, -0.04, -0.01), (s * 0.245, -0.38, 0), "shoulder" + side)
    JOINTS["hip" + side] = ((s * 0.1, -0.45, 0), (s * 0.1, -0.89, 0), "body")
    JOINTS["knee" + side] = ((s * 0.1, -0.89, 0), (s * 0.1, -1.33, 0.02), "hip" + side)

arm_data = bpy.data.armatures.new("rig")
rig = bpy.data.objects.new("rig", arm_data)
col.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = {}
for n, (h, tl, p) in JOINTS.items():
    b = arm_data.edit_bones.new(n); b.head = h; b.tail = tl; eb[n] = b
for n, (h, tl, p) in JOINTS.items():
    if p:
        eb[n].parent = eb[p]
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")

# ---------------- export: compact typed arrays (base64) for figure.js
me = body.data
nv = len(me.vertices)
pos = np.array([v.co[:] for v in me.vertices], dtype=np.float32)
nor = np.array([v.normal[:] for v in me.vertices], dtype=np.float32)
idx = np.array([p.vertices[:] for p in me.polygons], dtype=np.uint16).ravel()
names = list(JOINTS.keys())
gi = {g.index: names.index(g.name) for g in body.vertex_groups if g.name in names}
si = np.zeros((nv, 4), np.uint8); sw = np.zeros((nv, 4), np.float32)
unweighted = 0
for v in me.vertices:
    ws = sorted(((g.weight, gi[g.group]) for g in v.groups if g.group in gi and g.weight > 0.01), reverse=True)[:4]
    if not ws:
        unweighted += 1
        ws = [(1.0, 0)]
    tot = sum(w for w, _ in ws)
    for k, (w, b) in enumerate(ws):
        si[v.index, k] = b; sw[v.index, k] = w / tot
lo, hi = pos.min(0), pos.max(0)
q = np.round((pos - lo) / (hi - lo) * 65535).astype(np.uint16)
b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
out = {
    "version": 1, "vertices": nv, "triangles": len(idx) // 3,
    "bounds": [lo.tolist(), hi.tolist()],
    "position_u16": b64(q), "normal_i8": b64(np.round(nor * 127).astype(np.int8)),
    "index_u16": b64(idx), "skin_index_u8": b64(si), "skin_weight_u8": b64(np.round(sw * 255).astype(np.uint8)),
    "bones": [{"name": n, "pos": list(JOINTS[n][0]), "parent": JOINTS[n][2]} for n in names],
}
with open(f"{OUT}/mannequin.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))


# ---------------- diagnostics: cross-section at the strap, size, unweighted vertices
def section(y, tol=0.006):
    s = pos[np.abs(pos[:, 1] - y) < tol]
    t = s[np.abs(s[:, 0]) < 0.2]  # torso only (arms excluded by x)
    return [round(float(t[:, 0].max()), 3), round(float(t[:, 2].min()), 3), round(float(t[:, 2].max()), 3)]
print("STATS verts", nv, "tris", len(idx) // 3, "unweighted", unweighted, "bounds", lo.round(3), hi.round(3))
print("STRAP section y=0.13 (half-width, back z, front z):", section(0.13))
print("SECTION y=-0.45:", section(-0.33), "y=0.0:", section(0.0))

# ---------------- preview renders (workbench)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "SINGLE"
scene.display.shading.single_color = (0.78, 0.82, 0.9)
scene.render.resolution_x, scene.render.resolution_y = 700, 900
rig.hide_render = True
cam_data = bpy.data.cameras.new("cam"); cam_data.type = "ORTHO"; cam_data.ortho_scale = 2.2
cam = bpy.data.objects.new("cam", cam_data); col.objects.link(cam); scene.camera = cam
for name, loc, rot in (("front", (0, -0.3, 4), (0, 0, 0)), ("side", (4, -0.3, 0), (0, math.pi / 2, 0)),
                       ("three", (2.6, 0.2, 3.2), (-0.12, 0.68, 0))):
    cam.location = loc; cam.rotation_euler = rot
    scene.render.filepath = f"{OUT}/preview-{name}.png"
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=f"{OUT}/mannequin.blend")
# crotch close-up
cam.location = (0, -0.42, 2.0); cam.rotation_euler = (0, 0, 0); cam_data.ortho_scale = 0.6
scene.render.resolution_x = scene.render.resolution_y = 500
scene.render.filepath = f"{OUT}/preview-crotch.png"
bpy.ops.render.render(write_still=True)
