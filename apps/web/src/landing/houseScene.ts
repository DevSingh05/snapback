// @ts-nocheck
// The Worlds hero: an open dollhouse on its own lot, in a block of houses, drawn with three.js
// (orthographic, no photographs). Ported from the SNAPBACK Worlds page (v17), keeping the house
// that lifts apart floor by floor; the scripted check demo, photo fly-ins and DOM labels are left
// out. Pure drawing: it holds no claim about any real home. Colours come from the two palettes
// below (the Worlds Daylight / Dusk values), chosen by the page theme.
import * as THREE from "three";

export type Theme = "light" | "dark";

const PAL: Record<Theme, Record<string, string>> = {
  light: {
    sky: "#CFE0EA",
    ground: "#CEDBE3",
    block: "#F5F7F8",
    stone: "#D8CFC0",
    wall: "#FBFAF7",
    floor: "#CDAE86",
    glass: "#B4D3E6",
    dark: "#3A4A54",
    slab: "#EFEBE3",
    sofa: "#6E8597",
    rug: "#E6D9C6",
    road: "#C3D1DA",
    far: "#8FA6B6",
    cloud: "#FFFFFF",
    lawn: "#C5D6BA",
    leaf: "#86A886",
    roof: "#5F7483",
    act: "#0D6672",
    scan: "#DFA20A",
    mu: "#43555F",
  },
  dark: {
    sky: "#0E0F12",
    ground: "#202329",
    block: "#3A3E46",
    stone: "#A1988A",
    wall: "#D6D0C4",
    floor: "#B08D62",
    glass: "#6C9AB3",
    dark: "#15181C",
    slab: "#8E887C",
    sofa: "#6F8598",
    rug: "#A6987F",
    road: "#17191D",
    far: "#4A4F59",
    cloud: "#5A606B",
    lawn: "#2F3B33",
    leaf: "#4B6652",
    roof: "#4A5360",
    act: "#EEF3F5",
    scan: "#F2C14E",
    mu: "#BDB7AB",
  },
};

const PIT = 0.528;
const CD = 150;
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export interface HouseScene {
  setTheme(t: Theme): void;
  setVisible(v: boolean): void;
  dispose(): void;
}

export function mountHouse(
  cv: HTMLCanvasElement,
  el: HTMLElement,
  theme: Theme,
  reduced: boolean,
): HouseScene | null {
  let R;
  try {
    R = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  } catch {
    return null;
  }
  let th: Theme = theme;
  const binds: [any, string, string][] = [];
  const recolor = () => binds.forEach((b) => b[0][b[1]].set(PAL[th][b[2]]));
  R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  R.shadowMap.enabled = true;
  R.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene(),
    cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 440),
    rootG = new THREE.Group();
  scene.add(rootG);
  scene.fog = new THREE.Fog(0xffffff, 150, 206);
  binds.push([scene.fog, "color", "sky"]);
  const hemi = new THREE.HemisphereLight(0xffffff, 0xffffff, 0.62);
  binds.push([hemi, "groundColor", "ground"]);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xffffff, 0.45);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.bias = -0.0008;
  sun.shadow.radius = 3;
  const sc = sun.shadow.camera;
  sc.left = -26;
  sc.right = 26;
  sc.top = 26;
  sc.bottom = -26;
  sc.near = 1;
  sc.far = 90;
  scene.add(sun);
  scene.add(sun.target);
  const M = (t, o?) => {
    const m = new THREE.MeshStandardMaterial(
      Object.assign({ roughness: 0.94, metalness: 0 }, o || {}),
    );
    binds.push([m, "color", t]);
    return m;
  };
  const B = (t, o?) => {
    const m = new THREE.MeshBasicMaterial(
      Object.assign({ transparent: true, depthWrite: false }, o || {}),
    );
    binds.push([m, "color", t]);
    return m;
  };
  function box(p, w, h, d, x, y, z, mat, sh?) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x + w / 2, y + h / 2, z + d / 2);
    m.castShadow = sh !== false;
    m.receiveShadow = sh !== false;
    p.add(m);
    return m;
  }
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), M("ground"));
  // the scan points on the scanned surfaces
  const pu = {
    uScan: { value: -99 },
    uOn: { value: 0 },
    uBase: { value: 0 },
    uPx: { value: R.getPixelRatio() },
    uCol: { value: new THREE.Color() },
  };
  binds.push([pu.uCol, "value", "scan"]);
  const pm = new THREE.ShaderMaterial({
    uniforms: pu,
    transparent: true,
    depthWrite: false,
    vertexShader:
      "uniform float uScan,uOn,uBase,uPx;varying float vA;void main(){vec4 w=modelMatrix*vec4(position,1.);float g=exp(-abs(w.y-uScan)*1.4);vA=uBase+uOn*g;gl_Position=projectionMatrix*viewMatrix*w;gl_PointSize=uPx*(1.7+2.6*g*uOn);}",
    fragmentShader: "uniform vec3 uCol;varying float vA;void main(){gl_FragColor=vec4(uCol,vA);}",
  });
  const points = (parent, list) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(list.flat()), 3));
    const P = new THREE.Points(g, pm);
    P.frustumCulled = false;
    parent.add(P);
    return P;
  };
  const lattice = (W, D, H, s, o) => {
    const p = [];
    for (let x = s / 2; x < W; x += s) for (let z = s / 2; z < D; z += s) p.push([x, o + 0.04, z]);
    for (let y = s / 2; y < H; y += s) {
      for (let z = s / 2; z < D; z += s) p.push([o, y, z]);
      for (let x = s / 2; x < W; x += s) p.push([x, y, o]);
    }
    return p;
  };
  const mStone = M("stone"),
    mWall = M("wall"),
    mFloor = M("floor"),
    mSlab = M("slab"),
    mDark = M("dark"),
    mSofa = M("sofa"),
    mRug = M("rug"),
    mRoad = M("road"),
    mLawn = M("lawn"),
    mLeaf = M("leaf"),
    mRoof = M("roof");
  const mWin = new THREE.MeshStandardMaterial({ roughness: 0.25, emissiveIntensity: 0.25 });
  binds.push([mWin, "color", "glass"], [mWin, "emissive", "glass"]);
  const WS = [
    [-1, 0],
    [0, -1],
    [1, 0],
    [0, 1],
  ].map((n) => {
    const gl = new THREE.MeshStandardMaterial({
      roughness: 0.25,
      emissiveIntensity: 0.25,
      transparent: true,
    });
    binds.push([gl, "color", "glass"], [gl, "emissive", "glass"]);
    return {
      n,
      o: n[0] + n[1] < 0 ? 1 : 0,
      ms: [],
      st: M("stone", { transparent: true }),
      wl: M("wall", { transparent: true }),
      gl,
      dr: M("act", { transparent: true }),
    };
  });
  const pg = new THREE.GridHelper(43, 10);
  pg.position.set(-2.3, 0.015, -2.2);
  pg.material.transparent = true;
  pg.material.opacity = 0.2;
  pg.material.vertexColors = false;
  binds.push([pg.material, "color", "mu"]);
  rootG.add(pg);
  const fc = document.createElement("canvas");
  fc.width = fc.height = 64;
  const fx = fc.getContext("2d");
  fx.fillStyle = "#fff";
  fx.fillRect(0, 0, 64, 64);
  fx.fillStyle = "#b9c6d0";
  for (let c = 0; c < 2; c++) fx.fillRect(8 + c * 32, 18, 16, 30);
  const ftex = new THREE.CanvasTexture(fc);
  ftex.wrapS = ftex.wrapT = THREE.RepeatWrapping;
  const g0 = new THREE.Group();
  g0.rotation.y = Math.PI / 4;
  scene.add(g0);
  const gnd = new THREE.Mesh(new THREE.PlaneGeometry(600, 221), ground.material);
  gnd.rotation.x = -Math.PI / 2;
  gnd.position.z = 89.5;
  gnd.receiveShadow = true;
  g0.add(gnd);
  scene.fog.near = 151;
  scene.fog.far = 173;
  for (let i = -3; i <= 3; i++)
    box(rootG, 1.1, 0.02, 34, i * 4.3 - 2.85, 0, -16, mRoad, false).receiveShadow = true;
  for (let j = -3; j <= 3; j++)
    box(rootG, 34, 0.02, 1.1, -16, 0, j * 4.3 - 2.75, mRoad, false).receiveShadow = true;
  for (let i = -3; i <= 3; i++)
    for (let j = -3; j <= 2; j++) {
      if (
        (i === 0 && j === 0) ||
        (i === 1 && j === 0) ||
        (i === 0 && j === 1) ||
        (i === 1 && j === 1) ||
        (i === -1 && j === 0) ||
        (i === -2 && j === 1) ||
        (i === -1 && j === 1)
      )
        continue;
      let h = 1.1 + ((i * 7 + j * 13 + 60) % 5) * 0.5;
      if (i + j >= 0) h = 0.35 + ((i * 3 + j * 5 + 30) % 3) * 0.2;
      else if (i + j === -1) h = Math.min(h, 2.1);
      if (i === 0 && j === -2) h = 3.1;
      const w = 2.9 + ((i * 5 + j * 3 + 30) % 3) * 0.3,
        x = i * 4.3 - 1.6,
        z = j * 4.3 - 1.5,
        t = ftex.clone();
      t.needsUpdate = true;
      t.repeat.set(Math.round(w / 1.5), Math.max(1, Math.round(h / 0.9)));
      const side = new THREE.MeshStandardMaterial({
          roughness: 0.94,
          metalness: 0,
          map: h > 0.9 ? t : null,
        }),
        top = new THREE.MeshStandardMaterial({ roughness: 0.94, metalness: 0 });
      binds.push([side, "color", "block"], [top, "color", "block"]);
      const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, 3), [side, side, top, top, side, side]);
      m.position.set(x + w / 2, h / 2, z + 1.5);
      m.castShadow = m.receiveShadow = true;
      rootG.add(m);
      box(rootG, w - 0.5, 0.07, 2.5, x + 0.25, h, z + 0.25, mSlab);
      if ((i + j * 2 + 9) % 3 === 0 && h > 1)
        box(rootG, 0.7, 0.35, 0.6, x + 0.6, h + 0.07, z + 0.7, mStone);
    }
  scene.add(cam);
  const sk = document.createElement("canvas");
  sk.width = 1024;
  sk.height = 256;
  const sx = sk.getContext("2d");
  sx.fillStyle = "#fff";
  let rs = 11;
  const rr = () => {
    rs = (rs * 16807) % 2147483647;
    return rs / 2147483647;
  };
  for (let x = 0; x < 1010;) {
    const w = 14 + rr() * 30,
      c = Math.abs(x - 512) < 190 ? 1 : 0.45,
      h = (30 + rr() * 120) * c + 20;
    sx.fillRect(x, 256 - h, w - 3, h);
    if (rr() > 0.6) sx.fillRect(x + w * 0.25, 256 - h - 8 - rr() * 14, w * 0.4, 24);
    x += w;
  }
  const skT = new THREE.CanvasTexture(sk);
  skT.wrapS = THREE.RepeatWrapping;
  const skM = new THREE.MeshBasicMaterial({
    map: skT,
    transparent: true,
    opacity: 0.55,
    fog: false,
    depthWrite: false,
  });
  binds.push([skM, "color", "far"]);
  const sky = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), skM);
  cam.add(sky);
  const cc = document.createElement("canvas");
  cc.width = 512;
  cc.height = 128;
  const cx2 = cc.getContext("2d");
  [
    [90, 52, 150, 20],
    [300, 86, 180, 16],
    [440, 34, 110, 13],
  ].forEach((q) => {
    const g2 = cx2.createRadialGradient(0, 0, 0, 0, 0, 1);
    g2.addColorStop(0, "rgba(255,255,255,.95)");
    g2.addColorStop(1, "rgba(255,255,255,0)");
    cx2.save();
    cx2.translate(q[0], q[1]);
    cx2.scale(q[2], q[3]);
    cx2.fillStyle = g2;
    cx2.fillRect(-1, -1, 2, 2);
    cx2.restore();
  });
  const clT = new THREE.CanvasTexture(cc);
  clT.wrapS = THREE.RepeatWrapping;
  const clM = new THREE.MeshBasicMaterial({
    map: clT,
    transparent: true,
    opacity: 0.8,
    fog: false,
    depthWrite: false,
  });
  binds.push([clM, "color", "cloud"]);
  const cloud = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), clM);
  cam.add(cloud);

  // the home: an open dollhouse on its own lot
  const FH = 2.5,
    GAP = 1.9,
    W = 7,
    D = 4.6,
    floors = [],
    Ls = [];
  const Bd = new THREE.Group();
  Bd.position.set(-W / 2, 0, -D / 2);
  rootG.add(Bd);
  box(Bd, 11.7, 0.1, 7.8, -2.5, 0, -0.5, mLawn, false).receiveShadow = true;
  box(Bd, W + 0.6, 0.06, D + 0.6, -0.3, 0.1, -0.3, mSlab, false).receiveShadow = true;
  box(Bd, 0.9, 0.03, 2.4, 3.17, 0.1, D + 0.3, mSlab, false).receiveShadow = true;
  box(Bd, 1.9, 0.14, 0.8, 2.67, 0.1, D + 0.2, mStone);
  box(Bd, 1.5, 0.07, 0.3, 2.87, 0.1, D + 1.0, mStone);
  box(Bd, 1.8, 0.03, 6.6, W + 0.5, 0.1, 0.7, mRoad, false).receiveShadow = true;
  box(Bd, 1.3, 0.42, 2.7, W + 0.75, 0.26, 3.0, mSofa);
  box(Bd, 1.2, 0.4, 1.4, W + 0.8, 0.68, 3.5, mWin);
  [
    [W + 0.7, 3.3],
    [W + 1.9, 3.3],
    [W + 0.7, 5.0],
    [W + 1.9, 5.0],
  ].forEach((q) => box(Bd, 0.2, 0.4, 0.5, q[0], 0.1, q[1], mDark));
  box(Bd, 0.4, 0.5, 4.6, -2.4, 0.1, 2.6, mLeaf);
  box(Bd, 0.6, 0.45, 0.5, 1.6, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.6, 0.45, 0.5, 5.0, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.5, 0.34, 0.5, 5.65, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.26, 1.3, 0.26, -1.1, 0.1, D + 1.5, mFloor);
  box(Bd, 1.7, 1.0, 1.7, -1.82, 1.3, D + 0.78, mLeaf);
  box(Bd, 1.25, 0.8, 1.25, -1.6, 2.3, D + 1.0, mLeaf);
  box(Bd, 0.7, 0.6, 0.7, -1.32, 3.1, D + 1.28, mLeaf);
  [
    [-2.0, 3.0],
    [4.3, W + 0.4],
  ].forEach((r) => {
    box(Bd, r[1] - r[0], 0.07, 0.06, r[0], 0.5, 7.15, mWall);
    box(Bd, r[1] - r[0], 0.07, 0.06, r[0], 0.3, 7.15, mWall);
    for (let x = r[0]; x <= r[1] + 0.01; x += (r[1] - r[0]) / 8)
      box(Bd, 0.09, 0.56, 0.09, x - 0.045, 0.1, 7.13, mWall);
  });
  // the yard sign
  const sg = new THREE.Group();
  sg.position.set(1.0, 0.1, D + 1.6);
  Bd.add(sg);
  box(sg, 0.1, 2.4, 0.1, -0.05, 0, -0.05, mWall);
  box(sg, 1.8, 0.09, 0.1, -0.05, 2.24, -0.05, mWall);
  const sgc = document.createElement("canvas");
  sgc.width = 400;
  sgc.height = 280;
  {
    const x = sgc.getContext("2d");
    x.fillStyle = "#ffffff";
    x.fillRect(0, 0, 400, 280);
    x.fillStyle = "#0D6672";
    x.fillRect(0, 0, 400, 150);
    x.fillStyle = "#ffffff";
    x.textAlign = "center";
    x.textBaseline = "middle";
    x.font = '800 70px "Helvetica Neue",Arial,sans-serif';
    x.fillText("FOR SALE", 200, 80);
    x.fillStyle = "#14242D";
    x.font = '700 42px "Helvetica Neue",Arial,sans-serif';
    x.fillText("Another", 200, 190);
    x.fillText("brokerage", 200, 238);
  }
  const sgp = new THREE.Mesh(
    new THREE.PlaneGeometry(1.5, 1.05),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(sgc), side: THREE.DoubleSide }),
  );
  sgp.position.set(0.92, 1.66, 0);
  sg.add(sgp);
  for (let k = 0; k < 3; k++) {
    const g = new THREE.Group();
    Bd.add(g);
    floors.push(g);
    box(g, W + 0.2, 0.22, D + 0.2, -0.1, 0, -0.1, mSlab);
    box(g, W - 0.2, 0.03, D - 0.2, 0.1, 0.22, 0.1, mFloor, false).receiveShadow = true;
    const H = FH - 0.22,
      wm = (n, arr) => arr.forEach((m) => WS[n].ms.push(m));
    wm(0, [
      box(g, 0.18, H, D + 0.1, -0.1, 0.22, -0.1, WS[0].st),
      box(g, 0.04, H - 0.08, D - 0.1, 0.08, 0.22, 0.08, WS[0].wl, false),
      box(g, 0.04, 1.25, 1.3, 0.13, 0.85, 2.5, WS[0].gl, false),
    ]);
    wm(1, [
      box(g, W + 0.1, H, 0.18, -0.1, 0.22, -0.1, WS[1].st),
      box(g, W - 0.1, H - 0.08, 0.04, 0.08, 0.22, 0.08, WS[1].wl, false),
      box(g, 1.3, 1.25, 0.04, 2.0, 0.85, 0.13, WS[1].gl, false),
      box(g, 1.3, 1.25, 0.04, 4.8, 0.85, 0.13, WS[1].gl, false),
    ]);
    wm(2, [
      box(g, 0.18, H, D + 0.1, W - 0.08, 0.22, -0.1, WS[2].st),
      box(g, 0.04, H - 0.08, D - 0.1, W - 0.12, 0.22, 0.08, WS[2].wl, false),
      box(g, 0.04, 1.25, 1.3, W - 0.17, 0.85, 1.6, WS[2].gl, false),
    ]);
    wm(3, [
      box(g, W + 0.1, H, 0.18, -0.1, 0.22, D - 0.08, WS[3].st),
      box(g, W - 0.1, H - 0.08, 0.04, 0.08, 0.22, D - 0.12, WS[3].wl, false),
      box(g, 1.3, 1.25, 0.04, 1.6, 0.85, D - 0.17, WS[3].gl, false),
      box(g, 1.3, 1.25, 0.04, 4.4, 0.85, D - 0.17, WS[3].gl, false),
    ]);
    for (let q = 0; q < 5; q++)
      box(g, 1.0, (q + 1) * 0.44, 0.36, 0.14, 0.22, 0.14 + q * 0.36, mStone);
    if (k === 0) wm(3, [box(g, 1.05, 1.9, 0.34, 3.1, 0.22, D - 0.21, WS[3].dr, false)]);
    [
      [W - 0.06, D - 0.06],
      [W - 0.06, -0.02],
      [-0.02, D - 0.06],
    ].forEach((c) => box(g, 0.13, FH - 0.22, 0.13, c[0] - 0.06, 0.22, c[1] - 0.06, mDark));
    const L = new THREE.PointLight(0xffdfb6, 0.3, 8.5, 1.6);
    L.position.set(W * 0.55, FH - 0.5, D * 0.55);
    g.add(L);
    Ls.push(L);
    points(
      g,
      lattice(W - 0.3, D - 0.3, FH - 0.3, 0.3, 0.24).map((p) => [
        p[0] + 0.05,
        p[1] + 0.02,
        p[2] + 0.05,
      ]),
    );
  }
  const f2 = floors[2];
  box(f2, 0.1, 1.1, 2.3, 4.0, 0.25, 0.12, mWall);
  box(f2, 2.3, 0.02, 1.5, 4.4, 0.25, 2.6, mRug, false).receiveShadow = true;
  box(f2, 2.0, 0.42, 0.8, 4.55, 0.25, 3.55, mSofa);
  box(f2, 2.0, 0.5, 0.22, 4.55, 0.67, 4.13, mSofa);
  box(f2, 0.9, 0.3, 0.5, 5.1, 0.25, 2.8, mStone);
  box(f2, 1.5, 0.4, 2.0, 1.9, 0.25, 2.2, mWall);
  box(f2, 1.5, 0.14, 1.2, 1.9, 0.65, 3.0, mSofa);
  box(f2, 1.5, 0.7, 0.12, 1.9, 0.25, 2.08, mStone);
  const f1 = floors[1];
  box(f1, 0.6, 0.9, 2.1, 0.12, 0.25, 2.3, mStone);
  box(f1, 0.64, 0.05, 2.14, 0.1, 1.15, 2.28, mWall);
  box(f1, 1.6, 0.07, 0.9, 4.3, 0.95, 1.0, mStone);
  [
    [4.4, 1.1],
    [5.7, 1.1],
    [4.4, 1.75],
    [5.7, 1.75],
  ].forEach((q) => box(f1, 0.07, 0.7, 0.07, q[0], 0.25, q[1], mDark));
  [
    [4.6, 0.55],
    [5.3, 2.0],
  ].forEach((q) => box(f1, 0.42, 0.45, 0.42, q[0], 0.25, q[1], mSofa));
  box(f1, 2.4, 0.02, 1.6, 3.9, 0.25, 2.6, mRug, false).receiveShadow = true;
  const mPer = M("act");
  box(f1, 0.5, 1.15, 0.4, 2.5, 0.25, 2.6, mPer);
  box(f1, 0.34, 0.34, 0.34, 2.58, 1.43, 2.63, mWall);
  const f0 = floors[0];
  box(f0, 3.4, 0.9, 0.62, 3.3, 0.25, 0.14, mWall);
  box(f0, 3.5, 0.06, 0.7, 3.25, 1.15, 0.12, mDark);
  box(f0, 3.4, 0.55, 0.34, 3.3, 1.62, 0.14, mStone);
  box(f0, 0.75, 1.8, 0.66, 1.5, 0.25, 0.14, mSlab);
  box(f0, 2.0, 0.9, 0.75, 3.4, 0.25, 1.6, mStone);
  box(f0, 2.1, 0.06, 0.85, 3.35, 1.15, 1.55, mWall);
  [3.6, 4.5].forEach((q) => box(f0, 0.36, 0.6, 0.36, q, 0.25, 2.5, mSofa));
  box(f0, 1.6, 0.35, 0.5, 0.3, 0.25, 3.7, mSofa);
  box(f0, 2.6, 0.02, 1.4, 3.4, 0.25, 2.75, mRug, false).receiveShadow = true;
  const roof = new THREE.Group();
  Bd.add(roof);
  box(roof, W + 0.2, 0.22, D + 0.2, -0.1, 0, -0.1, mSlab);
  {
    const Rr = 1.75,
      hz = D / 2 + 0.1,
      ov = 0.45,
      a = Math.atan2(Rr, hz),
      L = (hz + ov) / Math.cos(a);
    [1, -1].forEach((q) => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(W + 1, 0.16, L), mRoof);
      m.position.set(W / 2, 0.28 + Rr - ((hz + ov) / 2) * Math.tan(a), D / 2 + (q * (hz + ov)) / 2);
      m.rotation.x = q * a;
      m.castShadow = m.receiveShadow = true;
      roof.add(m);
    });
    const tri = new THREE.Shape();
    tri.moveTo(-hz, 0);
    tri.lineTo(hz, 0);
    tri.lineTo(0, Rr);
    tri.closePath();
    [-0.1, W - 0.08].forEach((x) => {
      const m = new THREE.Mesh(
        new THREE.ExtrudeGeometry(tri, { depth: 0.18, bevelEnabled: false }),
        mStone,
      );
      m.rotation.y = Math.PI / 2;
      m.position.set(x, 0.22, D / 2);
      m.castShadow = m.receiveShadow = true;
      roof.add(m);
    });
    box(roof, W + 1.04, 0.12, 0.3, -0.52, 0.22 + Rr, D / 2 - 0.15, mRoof);
    box(roof, 0.75, 2.5, 0.75, 1.3, 0.22, 0.5, mStone);
    box(roof, 0.91, 0.12, 0.91, 1.22, 2.72, 0.42, mDark);
    box(roof, 1.3, 0.95, 1.5, 4.3, 0.4, D / 2 + 0.75, mWall);
    box(roof, 1.5, 0.1, 1.7, 4.2, 1.35, D / 2 + 0.65, mRoof);
    box(roof, 0.8, 0.5, 0.04, 4.55, 0.7, D / 2 + 2.25, mWin, false);
    box(roof, 0.05, 0.6, 0.7, W + 0.1, 0.7, D / 2 - 0.35, mWin, false);
  }
  const sheet = new THREE.Group();
  Bd.add(sheet);
  const mSh = B("scan", { opacity: 0.5 }),
    mSh2 = B("scan", { opacity: 0.1 });
  box(sheet, W + 1.2, 0.05, 0.07, -0.6, 0, -0.6, mSh, false);
  box(sheet, W + 1.2, 0.05, 0.07, -0.6, 0, D + 0.53, mSh, false);
  box(sheet, 0.07, 0.05, D + 1.2, -0.6, 0, -0.6, mSh, false);
  box(sheet, 0.07, 0.05, D + 1.2, W + 0.53, 0, -0.6, mSh, false);
  box(sheet, W + 1.2, 0.01, D + 1.2, -0.6, 0, -0.6, mSh2, false);
  recolor();

  let dim = { cw: 1, ch: 1 };
  const ob = { yaw: 0, yawT: 0, pit: PIT, pitT: PIT, idle: 0, last: 0 };
  const st = { open: 0, on: 0 };
  const t0 = performance.now();
  const setCam = (o) => {
    const c = cam;
    c.left = -o.cx / o.ppu;
    c.right = (dim.cw - o.cx) / o.ppu;
    c.top = o.cy / o.ppu;
    c.bottom = c.top - dim.ch / o.ppu;
    const cp = Math.cos(o.pit) * CD * 0.7071;
    c.position.set(cp, Math.sin(o.pit) * CD + o.y, cp);
    c.lookAt(0, o.y, 0);
    c.updateProjectionMatrix();
    c.updateMatrixWorld();
  };
  const cam1 = () => {
    const cw = dim.cw,
      ch = dim.ch,
      wide = cw > 900,
      ppu = Math.min(43, cw / 15.4, ch / 19.5);
    setCam({ ppu, cx: cw * (wide ? 0.66 : 0.5), cy: ch * (wide ? 0.58 : 0.62), y: 6, pit: ob.pit });
    const c = cam,
      wU = c.right - c.left,
      mx = (c.left + c.right) / 2,
      hz = 21 * Math.sin(ob.pit) - 6 * Math.cos(ob.pit),
      hU = (wide ? 120 : 84) / ppu,
      cU = (wide ? 56 : 40) / ppu;
    sky.scale.set(wU, hU, 1);
    sky.position.set(mx, hz - 14 / ppu + hU / 2, -(CD + 36));
    skT.repeat.x = wU / hU / 4;
    skT.offset.x = -ob.yaw * 0.15;
    cloud.scale.set(wU, cU, 1);
    cloud.position.set(mx, hz + (wide ? 92 : 64) / ppu, -(CD + 38));
    clT.repeat.x = wU / cU / 4;
    clT.offset.x = (reduced ? 0 : performance.now() * 0.000004) - ob.yaw * 0.08;
  };
  const size = () => {
    dim = { cw: el.clientWidth || 1, ch: el.clientHeight || 1 };
    R.setSize(dim.cw, dim.ch, false);
    cam1();
  };
  const ro = new ResizeObserver(size);
  ro.observe(el);
  size();

  // drag turns the block all the way round; a slow turn on its own after 4 s of rest
  const pt = new Map();
  const down = (e) => {
    pt.set(e.pointerId, [e.clientX, e.clientY]);
    cv.setPointerCapture(e.pointerId);
    cv.classList.add("drag");
  };
  const move = (e) => {
    const q = pt.get(e.pointerId);
    if (!q) return;
    ob.yawT += (e.clientX - q[0]) * 0.008;
    if (e.pointerType !== "touch") ob.pitT = clamp(ob.pitT + (e.clientY - q[1]) * 0.004, 0.3, 1.1);
    pt.set(e.pointerId, [e.clientX, e.clientY]);
    ob.idle = performance.now();
  };
  const up = (e) => {
    pt.delete(e.pointerId);
    if (!pt.size) cv.classList.remove("drag");
    ob.idle = performance.now();
  };
  cv.addEventListener("pointerdown", down);
  cv.addEventListener("pointermove", move);
  cv.addEventListener("pointerup", up);
  cv.addEventListener("pointercancel", up);

  let visible = true,
    raf = 0,
    dead = false;
  const frame = (now) => {
    raf = requestAnimationFrame(frame);
    if (!visible) return;
    ob.last = now;
    if (!reduced && !pt.size && now - ob.idle > 4000) {
      const base = Math.round(ob.yawT / (Math.PI * 2)) * Math.PI * 2;
      ob.yawT += (base + 0.4 * Math.sin(now * 0.00022) - ob.yawT) * 0.012;
      ob.pitT += (PIT - ob.pitT) * 0.012;
    }
    // the house lifts apart once, after a short beat, and stays open
    const target = reduced ? 1 : clamp((now - t0 - 500) / 1900, 0, 1);
    st.open = 1 - Math.pow(1 - target, 3);
    st.on = Math.min(1, st.open * 1.2);
    const kk = reduced ? 1 : 0.1;
    ob.yaw += (ob.yawT - ob.yaw) * kk;
    ob.pit += (ob.pitT - ob.pit) * kk;
    rootG.rotation.y = ob.yaw;
    cam1();
    const yw = ob.yaw,
      ccx = 0.7071 * (Math.cos(yw) - Math.sin(yw)),
      ccz = 0.7071 * (Math.sin(yw) + Math.cos(yw));
    WS.forEach((w) => {
      const t = clamp(0.5 - (w.n[0] * ccx + w.n[1] * ccz) / 0.3, 0, 1);
      w.o += (t - w.o) * (reduced ? 1 : 0.16);
      w.st.opacity = w.wl.opacity = w.gl.opacity = w.dr.opacity = w.o;
      const vv = w.o > 0.02;
      w.ms.forEach((m) => (m.visible = vv));
    });
    const lit = Math.floor(now / 2600) % 3;
    Ls.forEach((l, k) => (l.intensity = 0.3 + 0.45 * (st.open > 0.9 && k === lit ? 1 : 0)));
    sg.rotation.y = Math.PI / 4 - yw;
    const a = 0.75;
    sun.position.set(Math.cos(a) * 20, 25, Math.sin(a) * 20);
    const o = st.open;
    floors.forEach((g, k) => (g.position.y = 0.1 + k * FH + o * k * GAP));
    roof.position.y = 0.1 + 3 * FH + o * (2 * GAP + 1.7);
    const topY = 3 * FH + o * 2 * GAP,
      ph = reduced ? 0.55 : (now * 0.00016) % 1,
      sy = (ph < 0.5 ? ph * 2 : 2 - ph * 2) * topY;
    sheet.position.y = sy;
    sheet.visible = st.on > 0.02;
    pu.uScan.value = sy;
    pu.uOn.value = st.on;
    mSh.opacity = 0.7 * st.on;
    mSh2.opacity = 0.12 * st.on;
    R.render(scene, cam);
  };
  raf = requestAnimationFrame(frame);

  return {
    setTheme(t) {
      th = t;
      recolor();
    },
    setVisible(v) {
      visible = v;
    },
    dispose() {
      dead = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      cv.removeEventListener("pointerdown", down);
      cv.removeEventListener("pointermove", move);
      cv.removeEventListener("pointerup", up);
      cv.removeEventListener("pointercancel", up);
      scene.traverse((n) => {
        if (n.geometry) n.geometry.dispose();
        const m = n.material;
        if (m)
          (Array.isArray(m) ? m : [m]).forEach((x) => {
            if (x.map) x.map.dispose();
            x.dispose();
          });
      });
      R.dispose();
    },
  };
}
