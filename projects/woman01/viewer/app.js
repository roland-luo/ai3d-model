import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const OUTFITS = [
  {
    id: 'dress',
    name: '白裙漫步',
    en: 'WHITE DRESS',
    tag: '裙装',
    desc: '象牙白长裙，深色长发，适合有风的午后。',
    file: './assets/outfit_dress.glb',
    download: 'xiafeng_dress.glb'
  },
  {
    id: 'casual',
    name: '日常一刻',
    en: 'EVERYDAY',
    tag: '日常',
    desc: '白 T 与棕裤，干净利落，随时可以出门。',
    file: './assets/outfit_casual.glb',
    download: 'xiafeng_casual.glb'
  },
  {
    id: 'adventurer',
    name: '林间探险',
    en: 'TRAILBOUND',
    tag: '户外',
    desc: '苔绿探险装，背包与长靴，去山野里走一走。',
    file: './assets/outfit_adventurer.glb',
    download: 'xiafeng_adventurer.glb'
  }
];

const SKINS = [
  { hex: '#e8c0a2', name: '瓷白' },
  { hex: '#cd9468', name: '暖蜜' },
  { hex: '#a0693f', name: '麦色' }
];

const stagewrap = document.getElementById('stagewrap');
const canvas = document.getElementById('stage');
const loaderEl = document.getElementById('loader');
const loadbar = document.getElementById('loadbar');
const loadtext = document.getElementById('loadtext');

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  alpha: true,
  powerPreference: 'high-performance'
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearAlpha(0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.02;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 60);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.065;
controls.enablePan = false;
controls.rotateSpeed = 0.65;
controls.zoomSpeed = 0.8;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.55;
controls.minPolarAngle = 1.27;
controls.maxPolarAngle = 1.57;

const hemi = new THREE.HemisphereLight(0xdceeff, 0xf1e3ce, 1.2);
scene.add(hemi);

const key = new THREE.DirectionalLight(0xfff2dd, 2.15);
key.position.set(1.9, 5.2, 2.2);
key.target.position.set(0, 0.9, 0);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.left = -1.6;
key.shadow.camera.right = 1.6;
key.shadow.camera.top = 2.4;
key.shadow.camera.bottom = -0.5;
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 12;
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.018;
key.shadow.radius = 7;
scene.add(key);
scene.add(key.target);

const fill = new THREE.DirectionalLight(0xcfe4ff, 0.82);
fill.position.set(-2.7, 2.0, 1.8);
scene.add(fill);

const rim = new THREE.DirectionalLight(0xffe6c7, 1.35);
rim.position.set(-1.4, 2.9, -2.6);
scene.add(rim);

const bounce = new THREE.DirectionalLight(0xf6f0e4, 0.4);
bounce.position.set(0.2, 0.3, 3.0);
scene.add(bounce);

const shadowFloor = new THREE.Mesh(
  new THREE.CircleGeometry(2.1, 96),
  new THREE.ShadowMaterial({ color: 0x2e3b3f, opacity: 0.11 })
);
shadowFloor.rotation.x = -Math.PI / 2;
shadowFloor.receiveShadow = true;
shadowFloor.position.y = 0.001;
scene.add(shadowFloor);

{
  const contactCanvas = document.createElement('canvas');
  contactCanvas.width = 128;
  contactCanvas.height = 128;
  const ctx = contactCanvas.getContext('2d');
  const grad = ctx.createRadialGradient(64, 64, 4, 64, 64, 62);
  grad.addColorStop(0, 'rgba(40, 52, 56, 0.36)');
  grad.addColorStop(0.45, 'rgba(40, 52, 56, 0.16)');
  grad.addColorStop(1, 'rgba(40, 52, 56, 0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  const contactTex = new THREE.CanvasTexture(contactCanvas);
  contactTex.colorSpace = THREE.SRGBColorSpace;
  const contact = new THREE.Mesh(
    new THREE.PlaneGeometry(1.05, 0.62),
    new THREE.MeshBasicMaterial({
      map: contactTex,
      transparent: true,
      depthWrite: false,
      opacity: 0.9
    })
  );
  contact.rotation.x = -Math.PI / 2;
  contact.position.y = 0.002;
  scene.add(contact);
}

const ring = new THREE.Mesh(
  new THREE.RingGeometry(0.665, 0.669, 128),
  new THREE.MeshBasicMaterial({
    color: 0x5b7f93,
    transparent: true,
    opacity: 0.32,
    side: THREE.DoubleSide,
    depthWrite: false
  })
);
ring.rotation.x = -Math.PI / 2;
ring.position.y = 0.003;
scene.add(ring);

const dustGeo = new THREE.BufferGeometry();
{
  const count = 46;
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const r = 0.7 + Math.random() * 1.5;
    const a = Math.random() * Math.PI * 2;
    pos[i * 3] = Math.cos(a) * r;
    pos[i * 3 + 1] = 0.25 + Math.random() * 1.9;
    pos[i * 3 + 2] = Math.sin(a) * r;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
}
const dust = new THREE.Points(
  dustGeo,
  new THREE.PointsMaterial({
    color: 0xfff3d8,
    size: 0.014,
    transparent: true,
    opacity: 0.55,
    depthWrite: false,
    sizeAttenuation: true,
    blending: THREE.AdditiveBlending
  })
);
scene.add(dust);

const holder = new THREE.Group();
scene.add(holder);

const gltfLoader = new GLTFLoader();
const models = {};
const state = {
  outfit: 'dress',
  skin: SKINS[0].hex,
  skinName: SKINS[0].name,
  ready: false
};
let modelHeight = 1.84;
let homeView = null;
let viewTween = null;
let autoRotateResume = 0;

function base64ToBuffer(b64) {
  const bin = atob(b64);
  const len = bin.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

function loadOutfit(def) {
  return new Promise((resolve, reject) => {
    const embedded = window.EMBEDDED_MODELS && window.EMBEDDED_MODELS[def.id];
    if (embedded) {
      try {
        gltfLoader.parse(base64ToBuffer(embedded), '', resolve, reject);
      } catch (err) {
        reject(err);
      }
      return;
    }
    gltfLoader.load(def.file, resolve, undefined, reject);
  });
}

function measure(sceneRoot) {
  const box = new THREE.Box3();
  const tmp = new THREE.Box3();
  sceneRoot.traverse((obj) => {
    if (obj.isSkinnedMesh) {
      obj.computeBoundingBox();
      if (obj.boundingBox) {
        tmp.copy(obj.boundingBox).applyMatrix4(obj.matrixWorld);
        box.union(tmp);
      }
    } else if (obj.isMesh && obj.geometry) {
      obj.geometry.computeBoundingBox();
      if (obj.geometry.boundingBox) {
        tmp.copy(obj.geometry.boundingBox).applyMatrix4(obj.matrixWorld);
        box.union(tmp);
      }
    }
  });
  return box;
}

function applySkin(hex) {
  const color = new THREE.Color(hex);
  Object.values(models).forEach((entry) => {
    entry.root.traverse((obj) => {
      if (!obj.isMesh || !obj.material) return;
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      mats.forEach((mat) => {
        if (mat && /^skin/i.test(mat.name || '')) {
          mat.color.copy(color);
          mat.needsUpdate = true;
        }
      });
    });
  });
}

function fitCamera(updatePosition = true) {
  const w = stagewrap.clientWidth || 1;
  const h = stagewrap.clientHeight || 1;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();

  const targetY = modelHeight * 0.52;
  const vFov = THREE.MathUtils.degToRad(camera.fov);
  const distV = (modelHeight * 1.2) / (2 * Math.tan(vFov / 2));
  const distH = 1.08 / (2 * Math.tan(vFov / 2) * camera.aspect);
  const dist = Math.max(distV, distH);
  const target = new THREE.Vector3(0, targetY, 0);

  const polar = 1.43;
  const azimuth = 0.24;
  const pos = new THREE.Vector3(
    target.x + dist * Math.sin(polar) * Math.sin(azimuth),
    target.y + dist * Math.cos(polar),
    target.z + dist * Math.sin(polar) * Math.cos(azimuth)
  );

  controls.minDistance = dist * 0.55;
  controls.maxDistance = dist * 1.45;

  if (updatePosition) {
    controls.target.copy(target);
    camera.position.copy(pos);
    controls.update();
    homeView = {
      pos: pos.clone(),
      target: target.clone()
    };
  } else {
    controls.target.copy(target);
    controls.update();
  }
}

function flyHome() {
  if (!homeView) return;
  viewTween = {
    fromPos: camera.position.clone(),
    toPos: homeView.pos.clone(),
    fromTarget: controls.target.clone(),
    toTarget: homeView.target.clone(),
    start: performance.now(),
    duration: 620
  };
}

function updateViewTween(now) {
  if (!viewTween) return;
  const t = Math.min(1, (now - viewTween.start) / viewTween.duration);
  const e = 1 - Math.pow(1 - t, 3);
  camera.position.lerpVectors(viewTween.fromPos, viewTween.toPos, e);
  controls.target.lerpVectors(viewTween.fromTarget, viewTween.toTarget, e);
  if (t >= 1) viewTween = null;
}

function resize() {
  const w = stagewrap.clientWidth || 1;
  const h = stagewrap.clientHeight || 1;
  renderer.setSize(w, h, false);
  fitCamera(!state.ready);
}

new ResizeObserver(resize).observe(stagewrap);

async function boot() {
  try {
    let done = 0;
    for (const def of OUTFITS) {
      const gltf = await loadOutfit(def);
      const root = gltf.scene;
      const entry = new THREE.Group();
      entry.add(root);
      entry.visible = false;
      holder.add(entry);

      root.traverse((obj) => {
        if (!obj.isMesh) return;
        obj.castShadow = true;
        obj.receiveShadow = false;
        obj.frustumCulled = false;
        if (obj.material) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((mat) => {
            if (mat) mat.shadowSide = THREE.FrontSide;
          });
        }
      });

      const mixer = new THREE.AnimationMixer(root);
      if (gltf.animations && gltf.animations.length) {
        const action = mixer.clipAction(gltf.animations[0]);
        action.play();
      }
      mixer.update(0.016);
      root.updateMatrixWorld(true);

      const box = measure(root);
      const center = box.getCenter(new THREE.Vector3());
      root.position.x -= center.x;
      root.position.z -= center.z;
      root.position.y -= box.min.y;
      root.updateMatrixWorld(true);

      const h = box.max.y - box.min.y;
      if (def.id === 'dress') modelHeight = h;

      models[def.id] = {
        def,
        gltf,
        root,
        entry,
        mixer,
        entranceStart: 0
      };

      done += 1;
      loadbar.style.width = `${(done / OUTFITS.length) * 100}%`;
      loadtext.textContent = `载入衣橱 ${done} / ${OUTFITS.length}`;
    }

    applySkin(state.skin);
    weightsDone();
  } catch (err) {
    console.error('[viewer] load failed:', err);
    loadtext.textContent = '模型载入失败，请刷新页面重试';
    loadbar.style.width = '100%';
    loadbar.classList.add('is-error');
  }
}

function weightsDone() {
  state.ready = true;
  models.dress.entry.visible = true;
  models.dress.entranceStart = performance.now();
  resize();
  fitCamera(true);

  setTimeout(() => {
    loaderEl.classList.add('is-done');
    document.body.classList.add('is-ready');
    setTimeout(() => {
      loaderEl.setAttribute('hidden', '');
    }, 900);
  }, 220);
}

function updateMeta() {
  const def = OUTFITS.find((o) => o.id === state.outfit);
  const idx = OUTFITS.findIndex((o) => o.id === state.outfit);
  document.getElementById('modelIndex').textContent = String(idx + 1).padStart(2, '0');
  document.getElementById('outfitEn').textContent = def.en;
  document.getElementById('outfitDesc').textContent = def.desc;
  document.getElementById('outfitCount').textContent =
    `${String(idx + 1).padStart(2, '0')} / ${String(OUTFITS.length).padStart(2, '0')}`;

  document.querySelectorAll('.outfit').forEach((btn) => {
    const active = btn.dataset.outfit === state.outfit;
    btn.setAttribute('aria-pressed', String(active));
    btn.classList.toggle('is-active', active);
  });

  const caption = document.querySelector('.stage-caption');
  if (caption) {
    caption.classList.remove('is-in');
    void caption.offsetWidth;
    caption.classList.add('is-in');
  }
}

function setOutfit(id) {
  if (!models[id] || state.outfit === id) return;
  state.outfit = id;
  Object.entries(models).forEach(([key, entry]) => {
    entry.entry.visible = key === id;
  });
  models[id].entranceStart = performance.now();
  updateMeta();
}

function setSkin(hex, name) {
  state.skin = hex;
  state.skinName = name;
  applySkin(hex);
  document.querySelectorAll('.skin').forEach((btn) => {
    const active = btn.dataset.skin === hex;
    btn.setAttribute('aria-pressed', String(active));
    btn.classList.toggle('is-active', active);
  });
  const label = document.getElementById('skinName');
  label.textContent = name;
  label.classList.remove('is-in');
  void label.offsetWidth;
  label.classList.add('is-in');
}

function toast(message) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.classList.add('is-show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => el.classList.remove('is-show'), 2600);
}

async function downloadCurrent() {
  const def = OUTFITS.find((o) => o.id === state.outfit);
  try {
    let blob;
    const embedded = window.EMBEDDED_MODELS && window.EMBEDDED_MODELS[def.id];
    if (embedded) {
      blob = new Blob([base64ToBuffer(embedded)], { type: 'model/gltf-binary' });
    } else {
      const res = await fetch(def.file);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      blob = await res.blob();
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = def.download;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 8000);
    toast(`已保存「${def.name}」的 GLB 模型`);
  } catch (err) {
    console.error('[viewer] download failed:', err);
    toast('下载失败，请刷新页面后重试');
  }
}

function bindUi() {
  document.querySelectorAll('.outfit').forEach((btn) => {
    btn.addEventListener('click', () => setOutfit(btn.dataset.outfit));
  });

  document.querySelectorAll('.skin').forEach((btn) => {
    const skin = SKINS.find((s) => s.hex === btn.dataset.skin);
    btn.addEventListener('click', () => setSkin(btn.dataset.skin, skin ? skin.name : ''));
  });

  const rotateBtn = document.getElementById('rotateBtn');
  rotateBtn.addEventListener('click', () => {
    controls.autoRotate = !controls.autoRotate;
    rotateBtn.setAttribute('aria-pressed', String(controls.autoRotate));
    rotateBtn.classList.toggle('is-on', controls.autoRotate);
  });

  document.getElementById('resetBtn').addEventListener('click', () => {
    viewTween = null;
    flyHome();
  });

  document.getElementById('downloadBtn').addEventListener('click', downloadCurrent);

  controls.addEventListener('start', () => {
    autoRotateResume = 0;
    if (controls.autoRotate) controls.autoRotate = false;
  });
  controls.addEventListener('end', () => {
    if (rotateBtn.getAttribute('aria-pressed') === 'true') {
      autoRotateResume = performance.now() + 1800;
    }
  });

  const dialog = document.getElementById('licenseDialog');
  const openDialog = () => {
    dialog.removeAttribute('hidden');
    requestAnimationFrame(() => dialog.classList.add('is-open'));
    document.getElementById('licenseClose').focus();
  };
  const closeDialog = () => {
    dialog.classList.remove('is-open');
    setTimeout(() => dialog.setAttribute('hidden', ''), 240);
  };
  document.getElementById('licenseBtn').addEventListener('click', openDialog);
  document.getElementById('licenseClose').addEventListener('click', closeDialog);
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) closeDialog();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !dialog.hasAttribute('hidden')) closeDialog();
  });
}

bindUi();
resize();
updateMeta();

const clock = new THREE.Clock();
let dustPhase = 0;

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const now = performance.now();

  updateViewTween(now);
  if (autoRotateResume && now > autoRotateResume) {
    controls.autoRotate = true;
    autoRotateResume = 0;
  }
  controls.update();

  if (state.ready) {
    Object.values(models).forEach((entry) => {
      if (!entry.entry.visible) return;
      entry.mixer.update(dt);
      if (entry.entranceStart) {
        const t = Math.min(1, (now - entry.entranceStart) / 480);
        const e = 1 - Math.pow(1 - t, 3);
        const s = 0.982 + 0.018 * e;
        entry.entry.scale.setScalar(s);
        if (t >= 1) {
          entry.entry.scale.setScalar(1);
          entry.entranceStart = 0;
        }
      }
    });

    dustPhase += dt;
    const pos = dustGeo.getAttribute('position');
    for (let i = 0; i < pos.count; i++) {
      let y = pos.getY(i) + dt * 0.012;
      if (y > 2.25) y = 0.2;
      pos.setY(i, y);
    }
    pos.needsUpdate = true;
    dust.rotation.y = Math.sin(dustPhase * 0.06) * 0.02;
  }

  renderer.render(scene, camera);
}

boot();
animate();
