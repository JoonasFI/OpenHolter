// 3D posture figure. Loaded on demand with import(); rendering happens in the viewer's
// browser, the Mac mini only serves the files.
//
// Body frame (same as the calibration): x = body's right, y = towards the head, z = out of
// the chest. On the bed the head points to world -Z and the bed's long axis is world Z.
//   roll  (deg): rotation around the body's long axis, 0 = supine, +90 = left side down
//   pitch (deg): head end raised, 90 = sitting / standing
import * as THREE from "./vendor/three.module.min.js";

const SKIN = 0xc7d0e6, SKIN_DARK = 0x9aa6c2, STRAP = 0x161b26, POD = 0xff5470;
const MATTRESS_TOP = 0.0;
// the model is ~2.06 m in its own units; scale to an average adult (~1.77 m) so it fits the bed
const SIZE = 0.86;
const CHEST_Z = -0.25; // chest position along the bed; the head end is -Z

const mat = (color, rough = 0.55) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0.05, transparent: true });

// Articulated mannequin. Every limb hangs from a joint group, so poses are joint angles.
function buildBody() {
  const body = new THREE.Group();
  const parts = [];
  const joints = {};
  const put = (parent, mesh, x, y, z) => { mesh.position.set(x, y, z); parent.add(mesh); parts.push(mesh); return mesh; };
  const jointAt = (parent, name, x, y, z) => { const g = new THREE.Group(); g.position.set(x, y, z); parent.add(g); joints[name] = g; return g; };

  // torso: an elliptic capsule, wider than deep; origin of the body frame is the chest
  const torso = put(body, new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.36, 6, 18), mat(SKIN)), 0, 0.02, 0);
  torso.scale.set(1.18, 1, 0.74);
  const pelvis = put(body, new THREE.Mesh(new THREE.CapsuleGeometry(0.15, 0.06, 6, 18), mat(SKIN_DARK)), 0, -0.36, 0);
  pelvis.rotation.z = Math.PI / 2; pelvis.scale.set(0.95, 1.05, 0.8);

  const neck = jointAt(body, "neck", 0, 0.38, -0.01);
  put(neck, new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.06, 6, 12), mat(SKIN)), 0, 0.05, 0);
  const head = put(neck, new THREE.Mesh(new THREE.SphereGeometry(0.105, 24, 18), mat(SKIN, 0.5)), 0, 0.2, 0.02);
  head.scale.set(0.92, 1.12, 1);
  put(neck, new THREE.Mesh(new THREE.SphereGeometry(0.022, 10, 8), mat(SKIN_DARK)), 0, 0.2, 0.125); // nose: front/back at a glance

  for (const [side, s] of [["R", 1], ["L", -1]]) {
    const sh = jointAt(body, "shoulder" + side, s * 0.235, 0.27, -0.01);
    put(sh, new THREE.Mesh(new THREE.SphereGeometry(0.066, 14, 10), mat(SKIN)), 0, 0, 0);
    put(sh, new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.22, 6, 14), mat(SKIN)), 0, -0.16, 0);
    const el = jointAt(sh, "elbow" + side, 0, -0.31, 0);
    put(el, new THREE.Mesh(new THREE.CapsuleGeometry(0.043, 0.22, 6, 14), mat(SKIN)), 0, -0.14, 0);
    put(el, new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), mat(SKIN_DARK)), 0, -0.3, 0.01);

    const hip = jointAt(body, "hip" + side, s * 0.1, -0.45, 0);
    put(hip, new THREE.Mesh(new THREE.SphereGeometry(0.085, 14, 10), mat(SKIN)), 0, 0, 0);
    put(hip, new THREE.Mesh(new THREE.CapsuleGeometry(0.078, 0.32, 6, 14), mat(SKIN)), 0, -0.22, 0);
    const kn = jointAt(hip, "knee" + side, 0, -0.44, 0);
    put(kn, new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.32, 6, 14), mat(SKIN)), 0, -0.2, -0.005);
    // rounded foot: a flattened capsule pointing forward, with a small heel
    const foot = put(kn, new THREE.Mesh(new THREE.CapsuleGeometry(0.042, 0.13, 6, 16), mat(SKIN_DARK)), 0, -0.445, 0.055);
    foot.rotation.x = Math.PI / 2 - 0.12;
    foot.scale.set(1.08, 1, 0.62);
    put(kn, new THREE.Mesh(new THREE.SphereGeometry(0.045, 14, 10), mat(SKIN_DARK)), 0, -0.43, -0.005);
  }

  const { led } = addStrap(body, parts, 0.205, 0.66, 0.142);
  return { body, parts, torso, led, joints };
}

// chest strap + H10 pod (the thing that actually measures), sized to the torso at strap height
function addStrap(body, parts, radius, depthScale, podZ) {
  const strap = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 0.04, 40, 1, true),
    new THREE.MeshStandardMaterial({ color: STRAP, roughness: 0.8, side: THREE.DoubleSide, transparent: true }));
  strap.scale.set(1, 1, depthScale); strap.position.set(0, 0.13, 0); body.add(strap); parts.push(strap);
  const pod = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.05, 0.03),
    new THREE.MeshStandardMaterial({ color: 0x232a38, roughness: 0.4, metalness: 0.2, transparent: true }));
  pod.position.set(0, 0.13, podZ); body.add(pod); parts.push(pod);
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.012, 10, 8), new THREE.MeshBasicMaterial({ color: POD, transparent: true }));
  led.position.set(0, 0.13, podZ + 0.018); body.add(led); parts.push(led);
  const glow = new THREE.PointLight(POD, 0.18, 0.3);
  glow.position.set(0, 0.13, podZ + 0.08); body.add(glow);
  return { led };
}

// Smooth unisex mannequin modelled in Blender (scripts/blender/mannequin.py) and stored as
// compact typed arrays. Bones sit at the same joints as the primitive body, with identity
// rest orientation, so the pose angles below mean exactly the same for both.
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0)).buffer;
async function loadMannequin(url) {
  const d = await (await fetch(url)).json();
  const [lo, hi] = d.bounds;
  const q = new Uint16Array(b64(d.position_u16));
  const pos = new Float32Array(q.length);
  for (let i = 0; i < q.length; i++) { const k = i % 3; pos[i] = lo[k] + (q[i] / 65535) * (hi[k] - lo[k]); }
  const nrm = new Int8Array(b64(d.normal_i8));
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("normal", new THREE.BufferAttribute(nrm, 3, true));
  geo.setIndex(new THREE.BufferAttribute(new Uint16Array(b64(d.index_u16)), 1));
  geo.setAttribute("skinIndex", new THREE.BufferAttribute(new Uint8Array(b64(d.skin_index_u8)), 4));
  geo.setAttribute("skinWeight", new THREE.BufferAttribute(new Uint8Array(b64(d.skin_weight_u8)), 4, true));
  const mesh = new THREE.SkinnedMesh(geo, mat(SKIN, 0.5));
  const bones = {}, list = [];
  for (const b of d.bones) {
    const bone = new THREE.Bone(); bone.name = b.name;
    const p = b.parent ? d.bones.find((x) => x.name === b.parent).pos : [0, 0, 0];
    bone.position.set(b.pos[0] - p[0], b.pos[1] - p[1], b.pos[2] - p[2]);
    (b.parent ? bones[b.parent] : mesh).add(bone);
    bones[b.name] = bone; list.push(bone);
  }
  mesh.bind(new THREE.Skeleton(list));
  mesh.frustumCulled = false; // bounds are the rest pose
  const body = new THREE.Group();
  body.add(mesh);
  const parts = [mesh];
  const { led } = addStrap(body, parts, 0.182, 0.68, 0.134);
  const joints = {};
  for (const n of Object.keys(STRAIGHT)) joints[n] = bones[n];
  return { body, parts, torso: null, led, joints };
}

// ---- key poses (degrees per joint: [x, y, z]) in the body frame
// x: negative swings a limb forward (towards +z, the chest side); for elbows negative flexes,
// for knees positive flexes. z: positive moves a limb towards +x (the body's right).
const STRAIGHT = {
  neck: [0, 0, 0],
  shoulderR: [0, 0, 8], shoulderL: [0, 0, -8], elbowR: [-10, 0, 0], elbowL: [-10, 0, 0],
  hipR: [0, 0, 3], hipL: [0, 0, -3], kneeR: [4, 0, 0], kneeL: [4, 0, 0],
};
const SUPINE = STRAIGHT;
// side lying, `down` = side against the mattress: knees drawn up, top leg forward, arms in front
function sidePose(down) {
  const top = down === "L" ? "R" : "L", m = down === "L" ? 1 : -1; // m mirrors z for the other side
  return {
    neck: [8, 0, 14 * m],
    // lower arm forward under the pillow side, tilted up a little so it rests on (not in) the mattress
    ["shoulder" + down]: [-80, 0, 14 * m], ["elbow" + down]: [-70, 0, 0],
    // top arm relaxed: upper arm resting on the side, forearm down to the mattress in front of the belly
    ["shoulder" + top]: [-42, 0, -42 * m], ["elbow" + top]: [-55, 0, 0],
    // lower leg almost straight, upper leg resting a little forward with a soft knee
    ["hip" + down]: [-18, 0, 0], ["knee" + down]: [30, 0, 0],
    ["hip" + top]: [-38, 0, -10 * m], ["knee" + top]: [50, 0, 0],
  };
}
const LEFT = sidePose("L"), RIGHT = sidePose("R");
// prone: head turned, one arm up by the head, one knee drawn up and out
const PRONE = {
  neck: [-10, 70, 0],
  shoulderR: [-150, 0, 25], elbowR: [-95, 0, 0], shoulderL: [5, 0, -10], elbowL: [-5, 0, 0],
  hipR: [-25, 0, 22], kneeR: [55, 0, 0], hipL: [0, 0, -3], kneeL: [4, 0, 0],
};

function blendPose(roll, pitch) {
  const r = THREE.MathUtils.degToRad(roll);
  const c = Math.cos(r), sn = Math.sin(r);
  // smooth weights that sum to 1 over the full turn
  const w = [[SUPINE, Math.max(0, c) ** 2], [PRONE, Math.max(0, -c) ** 2], [sn >= 0 ? LEFT : RIGHT, sn * sn]];
  const up = Math.min(1, Math.max(0, (pitch - 30) / 45)); // sitting up straightens towards standing
  const out = {};
  for (const name of Object.keys(STRAIGHT)) {
    const v = [0, 0, 0];
    for (const [pose, k] of w) {
      const a = pose[name] || STRAIGHT[name];
      for (let i = 0; i < 3; i++) v[i] += a[i] * k;
    }
    for (let i = 0; i < 3; i++) v[i] = v[i] * (1 - up) + STRAIGHT[name][i] * up;
    out[name] = v;
  }
  return out;
}

function buildBed() {
  const bed = new THREE.Group();
  const mat = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.18, 2.15),
    new THREE.MeshStandardMaterial({ color: 0x1d2535, roughness: 0.95 }));
  mat.position.set(0, MATTRESS_TOP - 0.09, -0.05);
  bed.add(mat);
  const sheet = new THREE.Mesh(new THREE.BoxGeometry(1.06, 0.01, 2.16),
    new THREE.MeshStandardMaterial({ color: 0x27324a, roughness: 1 }));
  sheet.position.set(0, MATTRESS_TOP + 0.001, -0.05);
  bed.add(sheet);
  const pillow = new THREE.Mesh(new THREE.CapsuleGeometry(0.08, 0.42, 6, 16),
    new THREE.MeshStandardMaterial({ color: 0x313d58, roughness: 1 }));
  pillow.rotation.z = Math.PI / 2; pillow.scale.set(1, 1, 1.9);
  pillow.position.set(0, MATTRESS_TOP + 0.05, -0.86);
  bed.add(pillow);
  return bed;
}

const wrap = (a) => ((((a + 180) % 360) + 360) % 360) - 180;

export function createFigure(container, { interactive = false } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  } catch (e) {
    return null; // no WebGL: caller keeps its 2D fallback
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);
  renderer.domElement.className = "figure3d";

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 20);
  scene.add(new THREE.HemisphereLight(0xdfe6ff, 0x1a1f2e, 1.15));
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(1.6, 2.6, 1.4);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x8fa2ff, 0.9);
  rim.position.set(-2, 1.2, -2);
  scene.add(rim);

  scene.add(buildBed());
  // pitch (raise head end) -> base (lie down) -> roll (around the body's long axis)
  const pitchG = new THREE.Group();
  const base = new THREE.Group();
  base.rotation.x = -Math.PI / 2;
  const rollG = new THREE.Group();
  // The body frame (x = anatomical right, y = head, z = chest) is left-handed; three.js is
  // right-handed. Mirroring x puts the "R" limbs on the figure's real right side.
  const holder = new THREE.Group();
  holder.scale.set(-SIZE, SIZE, SIZE);
  rollG.add(holder);
  let rig = null; // { body, parts, torso, led, joints } once the mannequin has loaded
  const useRig = (r) => { holder.add(r.body); rig = r; applyGhost(); dirty = true; };
  loadMannequin(new URL("./mannequin.json", import.meta.url))
    .then(useRig)
    .catch(() => useRig(buildBody())); // older browser / file missing: primitive figure
  base.add(rollG);
  pitchG.add(base);
  pitchG.position.set(0, 0, CHEST_Z);
  scene.add(pitchG);

  // soft contact shadow
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(0.8, 1.7),
    new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.28, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.set(0, MATTRESS_TOP + 0.004, CHEST_Z + 0.02);
  scene.add(shadow);

  let target = { roll: 0, pitch: 0 }, cur = { roll: 0, pitch: 0 };
  let ghost = false, orbit = 0, raf = 0, last = 0, visible = true, dirty = true;
  function applyGhost() {
    if (!rig) return;
    for (const m of rig.parts) { m.material.opacity = ghost ? 0.35 : 1; m.material.depthWrite = !ghost; }
  }

  function layout() {
    const w = container.clientWidth || 200, h = container.clientHeight || 160;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // wide cards: three-quarter view from the foot end; narrow: a bit further back
    const dist = w / h < 1.1 ? 3.2 : 2.6;
    // seen from the foot end, slightly from world +X: lying on the left side the chest and strap face the camera
    const ang = 0.6 + orbit;
    camera.position.set(Math.sin(ang) * dist, 1.75, Math.cos(ang) * dist - 0.35);
    camera.lookAt(0, 0.12, -0.3);
    camera.updateProjectionMatrix();
    dirty = true;
  }

  function applyPose(t) {
    const r = THREE.MathUtils.degToRad(cur.roll), p = THREE.MathUtils.degToRad(Math.max(0, Math.min(90, cur.pitch)));
    rollG.rotation.y = r; // +90 = left side down (verified: anatomical right points up)
    pitchG.rotation.x = p;
    const pose = blendPose(cur.roll, cur.pitch);
    const d2r = THREE.MathUtils.degToRad;
    if (rig) for (const [name, [x, y, z]] of Object.entries(pose)) rig.joints[name].rotation.set(d2r(x), d2r(y), d2r(z));
    // rest on the mattress: half-depth when on the back/front, shoulder half-width on the side
    const lift = SIZE * Math.hypot(0.13 * Math.cos(r), 0.27 * Math.sin(r));
    // upright: raise so the feet (1.36 below the chest) stand on the mattress
    pitchG.position.y = MATTRESS_TOP + lift * Math.cos(p) + 1.36 * SIZE * Math.sin(p);
    pitchG.position.z = CHEST_Z - Math.sin(p) * 0.3;
    // breathing + strap LED pulse make the figure feel alive without being distracting
    if (rig && rig.torso) rig.torso.scale.set(1.18, 1, 0.74 * (1 + Math.sin(t / 900) * 0.012));
    if (rig) rig.led.material.opacity = 0.55 + 0.45 * Math.max(0, Math.sin(t / 260));
    shadow.material.opacity = 0.28 * Math.cos(p);
  }

  function frame(t) {
    raf = requestAnimationFrame(frame);
    if (!visible) return;
    if (t - last < 33) return; // ~30 fps is plenty
    const dt = Math.min(0.1, (t - last) / 1000);
    last = t;
    const k = 1 - Math.exp(-dt * 5);
    const dr = wrap(target.roll - cur.roll), dp = target.pitch - cur.pitch;
    if (Math.abs(dr) > 0.05 || Math.abs(dp) > 0.05) { cur.roll = wrap(cur.roll + dr * k); cur.pitch += dp * k; dirty = true; }
    if (interactive) { orbit = Math.sin(t / 7000) * 0.35; layout(); }
    applyPose(t);
    renderer.render(scene, camera);
  }

  const ro = new ResizeObserver(layout);
  ro.observe(container);
  const io = new IntersectionObserver((e) => { visible = e[0].isIntersecting; });
  io.observe(container);
  layout();
  raf = requestAnimationFrame(frame);

  return {
    setPose(roll, pitch = 0, immediate = false) {
      target = { roll, pitch };
      if (immediate) cur = { roll, pitch };
    },
    setGhost(on) {
      if (on === ghost) return;
      ghost = on;
      applyGhost();
    },
    dispose() {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect();
      renderer.dispose(); renderer.domElement.remove();
    },
  };
}

export const POSE = { supine: [0, 0], left: [90, 0], right: [-90, 0], prone: [180, 0], upright: [0, 80] };
