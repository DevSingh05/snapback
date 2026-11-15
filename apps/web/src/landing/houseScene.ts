// The Worlds hero: an open dollhouse on its own lot, in a block of houses, drawn with three.js
// (orthographic). Ported from the SNAPBACK Worlds page (v17). The page's scroll drives it: the
// house lifts apart floor by floor, the ad's sample photos fly to the walls they were taken at,
// then a gold marker goes to the yard sign (the home's record). Pure drawing: it holds no claim
// about any real home. Colours are the Worlds Daylight values below (Day only, like the app).
import * as THREE from "three";

const PAL: Record<string, string> = {
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
};

type Bind = [object, string, string];
const PIT = 0.528;
const CD = 150;
const ctx2d = (c: HTMLCanvasElement): CanvasRenderingContext2D => {
  const x = c.getContext("2d");
  if (!x) throw new Error("no 2d canvas");
  return x;
};
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

const seg = (v: number, a: number, b: number) => clamp((v - a) / (b - a), 0, 1);
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const back = (t: number) => {
  const u = clamp(t, 0, 1) - 1;
  return 1 + 2.4 * u * u * u + 1.4 * u * u;
};

export interface HouseScene {
  setVisible(v: boolean): void;
  /** 0 at the top of the scroll stage, 1 at its end. */
  setProgress(p: number): void;
  dispose(): void;
}

export interface HouseOpts {
  /** Three sample photos from "the ad"; they fly to the top floor's walls. */
  photos?: string[];
  /** DOM labels pinned to the drawing: one per floor (ground first) and one for the yard sign. */
  floorLabels?: (HTMLElement | null)[];
  signLabel?: HTMLElement | null;
}

export function mountHouse(
  cv: HTMLCanvasElement,
  el: HTMLElement,
  reduced: boolean,
  opts: HouseOpts = {},
): HouseScene | null {
  let R: THREE.WebGLRenderer;
  try {
    R = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  } catch {
    return null;
  }
  const binds: Bind[] = [];
  const recolor = () =>
    binds.forEach((b) => (b[0] as Record<string, THREE.Color>)[b[1]]?.set(PAL[b[2]] ?? "#ffffff"));
  R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  R.shadowMap.enabled = true;
  R.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene(),
    cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 440),
    rootG = new THREE.Group();
  scene.add(rootG);
  const fog = new THREE.Fog(0xffffff, 150, 206);
  scene.fog = fog;
  binds.push([fog, "color", "sky"]);
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
  const M = (t: string, o?: THREE.MeshStandardMaterialParameters) => {
    const m = new THREE.MeshStandardMaterial(
      Object.assign({ roughness: 0.94, metalness: 0 }, o || {}),
    );
    binds.push([m, "color", t]);
    return m;
  };
  const B = (t: string, o?: THREE.MeshBasicMaterialParameters) => {
    const m = new THREE.MeshBasicMaterial(
      Object.assign({ transparent: true, depthWrite: false }, o || {}),
    );
    binds.push([m, "color", t]);
    return m;
  };
  function box(
    p: THREE.Object3D,
    w: number,
    h: number,
    d: number,
    x: number,
    y: number,
    z: number,
    mat: THREE.Material,
    sh?: boolean,
  ) {
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
  const points = (parent: THREE.Object3D, list: number[][]) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(list.flat()), 3));
    const P = new THREE.Points(g, pm);
    P.frustumCulled = false;
    parent.add(P);
    return P;
  };
  const lattice = (W: number, D: number, H: number, s: number, o: number) => {
    const p: [number, number, number][] = [];
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
  const side = (n: [number, number]) => {
    const gl = new THREE.MeshStandardMaterial({
      roughness: 0.25,
      emissiveIntensity: 0.25,
      transparent: true,
    });
    binds.push([gl, "color", "glass"], [gl, "emissive", "glass"]);
    return {
      n,
      o: n[0] + n[1] < 0 ? 1 : 0,
      ms: [] as THREE.Object3D[],
      st: M("stone", { transparent: true }),
      wl: M("wall", { transparent: true }),
      gl,
      dr: M("act", { transparent: true }),
    };
  };
  const WS = [side([-1, 0]), side([0, -1]), side([1, 0]), side([0, 1])] as const;
  const pg = new THREE.GridHelper(43, 10);
  pg.position.set(-2.3, 0.015, -2.2);
  const pgm = pg.material as THREE.LineBasicMaterial;
  pgm.transparent = true;
  pgm.opacity = 0.2;
  pgm.vertexColors = false;
  binds.push([pgm, "color", "mu"]);
  rootG.add(pg);
  const fc = document.createElement("canvas");
  fc.width = fc.height = 64;
  const fx = ctx2d(fc);
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
  fog.near = 151;
  fog.far = 173;
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
  const sx = ctx2d(sk);
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
  const cx2 = ctx2d(cc);
  (
    [
      [90, 52, 150, 20],
      [300, 86, 180, 16],
      [440, 34, 110, 13],
    ] as [number, number, number, number][]
  ).forEach((q) => {
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
    floors: THREE.Group[] = [],
    Ls: THREE.PointLight[] = [];
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
  (
    [
      [W + 0.7, 3.3],
      [W + 1.9, 3.3],
      [W + 0.7, 5.0],
      [W + 1.9, 5.0],
    ] as [number, number][]
  ).forEach((q) => box(Bd, 0.2, 0.4, 0.5, q[0], 0.1, q[1], mDark));
  box(Bd, 0.4, 0.5, 4.6, -2.4, 0.1, 2.6, mLeaf);
  box(Bd, 0.6, 0.45, 0.5, 1.6, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.6, 0.45, 0.5, 5.0, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.5, 0.34, 0.5, 5.65, 0.1, D + 0.25, mLeaf);
  box(Bd, 0.26, 1.3, 0.26, -1.1, 0.1, D + 1.5, mFloor);
  box(Bd, 1.7, 1.0, 1.7, -1.82, 1.3, D + 0.78, mLeaf);
  box(Bd, 1.25, 0.8, 1.25, -1.6, 2.3, D + 1.0, mLeaf);
  box(Bd, 0.7, 0.6, 0.7, -1.32, 3.1, D + 1.28, mLeaf);
  (
    [
      [-2.0, 3.0],
      [4.3, W + 0.4],
    ] as [number, number][]
  ).forEach((r) => {
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
    const x = ctx2d(sgc);
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
      wm = (n: 0 | 1 | 2 | 3, arr: THREE.Object3D[]) => arr.forEach((m) => WS[n].ms.push(m));
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
    (
      [
        [W - 0.06, D - 0.06],
        [W - 0.06, -0.02],
        [-0.02, D - 0.06],
      ] as [number, number][]
    ).forEach((c) => box(g, 0.13, FH - 0.22, 0.13, c[0] - 0.06, 0.22, c[1] - 0.06, mDark));
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
  const [f0, f1, f2] = floors;
  if (!f0 || !f1 || !f2) return null;
  box(f2, 0.1, 1.1, 2.3, 4.0, 0.25, 0.12, mWall);
  box(f2, 2.3, 0.02, 1.5, 4.4, 0.25, 2.6, mRug, false).receiveShadow = true;
  box(f2, 2.0, 0.42, 0.8, 4.55, 0.25, 3.55, mSofa);
  box(f2, 2.0, 0.5, 0.22, 4.55, 0.67, 4.13, mSofa);
  box(f2, 0.9, 0.3, 0.5, 5.1, 0.25, 2.8, mStone);
  box(f2, 1.5, 0.4, 2.0, 1.9, 0.25, 2.2, mWall);
  box(f2, 1.5, 0.14, 1.2, 1.9, 0.65, 3.0, mSofa);
  box(f2, 1.5, 0.7, 0.12, 1.9, 0.25, 2.08, mStone);
  box(f1, 0.6, 0.9, 2.1, 0.12, 0.25, 2.3, mStone);
  box(f1, 0.64, 0.05, 2.14, 0.1, 1.15, 2.28, mWall);
  box(f1, 1.6, 0.07, 0.9, 4.3, 0.95, 1.0, mStone);
  (
    [
      [4.4, 1.1],
      [5.7, 1.1],
      [4.4, 1.75],
      [5.7, 1.75],
    ] as [number, number][]
  ).forEach((q) => box(f1, 0.07, 0.7, 0.07, q[0], 0.25, q[1], mDark));
  (
    [
      [4.6, 0.55],
      [5.3, 2.0],
    ] as [number, number][]
  ).forEach((q) => box(f1, 0.42, 0.45, 0.42, q[0], 0.25, q[1], mSofa));
  box(f1, 2.4, 0.02, 1.6, 3.9, 0.25, 2.6, mRug, false).receiveShadow = true;
  const mPer = M("act");
  box(f1, 0.5, 1.15, 0.4, 2.5, 0.25, 2.6, mPer);
  box(f1, 0.34, 0.34, 0.34, 2.58, 1.43, 2.63, mWall);
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

  // the ad's photos: each flies in and locks onto the wall it was taken at
  const TL = new THREE.TextureLoader();
  // they come from the side the ad's card sits on (screen left, towards the viewer)
  const off = new THREE.Vector3(-0.4, 4, 12.4),
    cWhite = new THREE.Color(0xffffff),
    cGold = new THREE.Color(PAL.scan);
  type Flying = {
    g: THREE.Group;
    slot: THREE.Vector3;
    bm: THREE.MeshBasicMaterial;
    im: THREE.MeshBasicMaterial;
  };
  const photos: Flying[] = [];
  const photo = (src: string, x: number, y: number, z: number, ry: number) => {
    const g = new THREE.Group();
    const bm = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      side: THREE.DoubleSide,
    });
    const tex = TL.load(src, (t) => {
      const img = t.image as { width: number; height: number };
      const ia = img.width / img.height,
        sa = 1.88 / 1.28;
      if (ia > sa) {
        t.repeat.x = sa / ia;
        t.offset.x = (1 - t.repeat.x) / 2;
      } else {
        t.repeat.y = ia / sa;
        t.offset.y = (1 - t.repeat.y) / 2;
      }
    });
    const im = new THREE.MeshBasicMaterial({ map: tex, transparent: true });
    g.add(new THREE.Mesh(new THREE.PlaneGeometry(2.0, 1.4), bm));
    const ip = new THREE.Mesh(new THREE.PlaneGeometry(1.88, 1.28), im);
    ip.position.z = 0.02;
    g.add(ip);
    g.rotation.y = ry;
    g.visible = false;
    f2.add(g);
    photos.push({ g, slot: new THREE.Vector3(x, y, z), bm, im });
  };
  const SLOTS: [number, number, number, number][] = [
    [0.2, 1.5, 3.15, Math.PI / 2],
    [2.65, 1.5, 0.2, 0],
    [5.45, 1.5, 0.2, 0],
  ];
  (opts.photos ?? []).slice(0, 3).forEach((src, i) => {
    const q = SLOTS[i];
    if (q) photo(src, q[0], q[1], q[2], q[3]);
  });
  // our marker: the gold matched point from the mark, floating over whatever is being checked
  const mk = new THREE.Group();
  rootG.add(mk);
  const mkM = B("scan", { opacity: 1, depthTest: false });
  const mkA = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.62, 0.08), mkM);
  mkA.renderOrder = 8;
  mk.add(mkA);
  const mkB = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.6, 0.08), mkM);
  mkB.position.y = -0.62;
  mkB.renderOrder = 8;
  mk.add(mkB);
  mk.visible = false;
  const mkP = new THREE.Vector3(0, 12, 0),
    mkT = new THREE.Vector3(),
    v3 = new THREE.Vector3();
  recolor();

  let dim = { cw: 1, ch: 1 };
  const ob = { yaw: 0, yawT: 0, pit: PIT, pitT: PIT, idle: 0, last: 0 };
  const st = { open: 0, on: 0, p: reduced ? 1 : 0, pT: reduced ? 1 : 0 };
  const t0 = performance.now();
  const fl = [0, 0, 0];
  const lbl = new Map<HTMLElement, { x: number; y: number; o: string }>();
  const put = (n: HTMLElement, v: THREE.Vector3, dx: number, dy: number, show: boolean) => {
    v.project(cam);
    const x = clamp(((v.x + 1) / 2) * dim.cw + dx, 8, dim.cw - (dim.cw > 900 ? 200 : 132)),
      y = clamp(((1 - v.y) / 2) * dim.ch + dy, 8, dim.ch - 44);
    let c = lbl.get(n);
    if (!c) lbl.set(n, (c = { x, y, o: "" }));
    c.x += (x - c.x) * (reduced ? 1 : 0.2);
    c.y += (y - c.y) * (reduced ? 1 : 0.2);
    n.style.transform = `translate3d(${c.x.toFixed(1)}px,${c.y.toFixed(1)}px,0)`;
    const o = show ? "1" : "0";
    if (o !== c.o) n.style.opacity = c.o = o;
  };
  const setCam = (o: { cx: number; cy: number; ppu: number; y: number; pit: number }) => {
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
      // the camera leans in to the top floor while the photos land, then down to the yard sign
      ca = ease(seg(st.p, 0.28, 0.4)),
      cb = ease(seg(st.p, 0.6, 0.74)),
      cy0 = 6 + 2.2 * ca - 2.8 * cb,
      ppu = Math.min(58, cw / 15.4, ch / (wide ? 19.5 : 30)) * (1 + 0.16 * ca - 0.1 * cb);
    setCam({
      ppu,
      cx: cw * (wide ? (cw < 1200 ? 0.72 : 0.66) : 0.5),
      cy: ch * (wide ? 0.56 : 0.27),
      y: cy0,
      pit: ob.pit,
    });
    const c = cam,
      wU = c.right - c.left,
      mx = (c.left + c.right) / 2,
      hz = 21 * Math.sin(ob.pit) - cy0 * Math.cos(ob.pit),
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
  const pt = new Map<number, [number, number]>();
  const down = (e: PointerEvent) => {
    pt.set(e.pointerId, [e.clientX, e.clientY]);
    cv.setPointerCapture(e.pointerId);
    cv.classList.add("drag");
  };
  // Hover (mouse only): the floor under the pointer lifts a little and its label lights, so
  // the drawing answers the hand. One ray per frame at most.
  const ray = new THREE.Raycaster(),
    ndc = new THREE.Vector2(),
    hov = [0, 0, 0];
  let hot = -1,
    hoverAt: [number, number] | null = null;
  const pick = () => {
    if (!hoverAt) return -1;
    const r = cv.getBoundingClientRect();
    ndc.set(((hoverAt[0] - r.left) / r.width) * 2 - 1, -((hoverAt[1] - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, cam);
    const hit = ray.intersectObjects(floors, true).find((h) => h.object instanceof THREE.Mesh);
    for (let o: THREE.Object3D | null = hit?.object ?? null; o; o = o.parent) {
      const k = floors.indexOf(o as THREE.Group);
      if (k >= 0) return k;
    }
    return -1;
  };
  const leave = () => {
    hoverAt = null;
  };
  cv.addEventListener("pointerleave", leave);
  const move = (e: PointerEvent) => {
    if (e.pointerType === "mouse" && !pt.size) hoverAt = [e.clientX, e.clientY];
    const q = pt.get(e.pointerId);
    if (!q) return;
    ob.yawT += (e.clientX - q[0]) * 0.008;
    if (e.pointerType !== "touch") ob.pitT = clamp(ob.pitT + (e.clientY - q[1]) * 0.004, 0.3, 1.1);
    pt.set(e.pointerId, [e.clientX, e.clientY]);
    ob.idle = performance.now();
  };
  const up = (e: PointerEvent) => {
    pt.delete(e.pointerId);
    if (!pt.size) cv.classList.remove("drag");
    ob.idle = performance.now();
  };
  cv.addEventListener("pointerdown", down);
  cv.addEventListener("pointermove", move);
  cv.addEventListener("pointerup", up);
  cv.addEventListener("pointercancel", up);

  let visible = true,
    raf = 0;
  const frame = (now: number) => {
    raf = requestAnimationFrame(frame);
    if (!visible) return;
    ob.last = now;
    if (!reduced && !pt.size && now - ob.idle > 4000) {
      const base = Math.round(ob.yawT / (Math.PI * 2)) * Math.PI * 2;
      ob.yawT += (base + 0.4 * Math.sin(now * 0.00022) - ob.yawT) * 0.012;
      ob.pitT += (PIT - ob.pitT) * 0.012;
    }
    // Scroll is the clock. The page sets pT; the drawing eases after it, so a wheel tick or a
    // flick never jumps. On load the floors part a little on their own, to say "this opens".
    st.p += (st.pT - st.p) * (reduced ? 1 : 0.11);
    const p = st.p,
      hint = reduced ? 0 : 0.1 * ease(clamp((now - t0 - 500) / 1500, 0, 1));
    st.open = Math.max(hint, ease(seg(p, 0.04, 0.28)));
    st.on = Math.min(1, st.open * 1.2);
    const rec = seg(p, 0.64, 0.8);
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
    // the floor being checked warms up: the top floor while the photos land, the ground floor
    // while the record is read
    const want = rec > 0.2 ? 0 : p > 0.32 ? 2 : -1;
    Ls.forEach((l, k) => {
      fl[k] = (fl[k] ?? 0) + ((k === want ? 1 : 0) - (fl[k] ?? 0)) * (reduced ? 1 : 0.08);
      l.intensity = 0.3 + 0.45 * Math.max(fl[k] ?? 0, hov[k] ?? 0);
    });
    sg.rotation.y = Math.PI / 4 - yw;
    const a = 0.75 + 0.35 * seg(p, 0.32, 0.6) - 0.65 * rec;
    sun.position.set(Math.cos(a) * 20, 25, Math.sin(a) * 20);
    const o = st.open;
    if (hoverAt || hot >= 0) {
      const k = !reduced && st.open > 0.6 && !pt.size ? pick() : -1;
      if (k !== hot) {
        const lbls = opts.floorLabels ?? [];
        lbls[hot]?.classList.remove("is-hot");
        lbls[k]?.classList.add("is-hot");
        hot = k;
      }
    }
    floors.forEach((g, k) => {
      hov[k] = (hov[k] ?? 0) + ((k === hot ? 1 : 0) - (hov[k] ?? 0)) * 0.14;
      g.position.y = 0.1 + k * FH + o * k * GAP + 0.28 * (hov[k] ?? 0);
    });
    // the roof rises clear of the top floor while the photos land on its far walls
    roof.position.y =
      0.1 +
      3 * FH +
      o * (2 * GAP + 1.7) +
      3.4 * ease(seg(p, 0.28, 0.4)) * (1 - ease(seg(p, 0.6, 0.74)));
    const topY = 3 * FH + o * 2 * GAP,
      ph = reduced ? 0.55 : (now * 0.00016) % 1,
      sy = (ph < 0.5 ? ph * 2 : 2 - ph * 2) * topY;
    sheet.position.y = sy;
    sheet.visible = st.on > 0.02;
    pu.uScan.value = sy;
    pu.uOn.value = st.on;
    mSh.opacity = 0.7 * st.on;
    mSh2.opacity = 0.12 * st.on;
    let landed = 0;
    photos.forEach((f, i) => {
      const q = seg(p, 0.32 + i * 0.07, 0.44 + i * 0.07);
      f.g.visible = q > 0.001;
      f.g.position.copy(f.slot).addScaledVector(off, 1 - back(q));
      f.g.scale.setScalar(1 + 1.5 * (1 - ease(q)));
      f.bm.opacity = f.im.opacity = Math.min(1, q * 3);
      // a gold flash on the frame as it locks on
      f.bm.color.copy(cWhite).lerp(cGold, Math.sin(seg(q, 0.8, 1) * Math.PI));
      if (q > 0.98) landed = i + 1;
    });
    // the marker: over the home, then over each photo as it lands, then at the yard sign
    rootG.updateMatrixWorld(true);
    const s0 = photos[Math.min(landed, photos.length - 1)]?.slot;
    if (rec > 0.02) f0.localToWorld(mkT.set(1.9, 3.5, D + 1.6));
    else if (p > 0.32 && s0) f2.localToWorld(mkT.set(s0.x + 0.4, 3.0, s0.z + 0.4));
    else f2.localToWorld(mkT.set(W / 2, FH + 1.0, D / 2));
    rootG.worldToLocal(mkT);
    mkP.lerp(mkT, reduced ? 1 : 0.12);
    mk.position.copy(mkP);
    if (!reduced) mk.position.y += Math.sin(now * 0.003) * 0.12;
    mk.rotation.y = Math.PI / 4 - yw;
    const mkv = seg(p, 0.1, 0.2);
    mk.visible = mkv > 0.02;
    mk.scale.setScalar(Math.max(0.01, mkv) * (1 + (reduced ? 0 : 0.12 * Math.sin(now * 0.006))));
    R.render(scene, cam);
    (opts.floorLabels ?? []).forEach((n, k) => {
      const g = floors[k];
      if (!n || !g) return;
      let bx = -1e9,
        by = 0;
      (
        [
          [W + 0.3, -0.3],
          [W + 0.3, D + 0.3],
          [-0.3, D + 0.3],
          [-0.3, -0.3],
        ] as [number, number][]
      ).forEach((c) => {
        g.localToWorld(v3.set(c[0], 1.25, c[1])).project(cam);
        if (v3.x > bx) {
          bx = v3.x;
          by = v3.y;
        }
      });
      put(n, v3.set(bx, by, 0).unproject(cam), 10, -16, st.open > 0.55);
    });
    if (opts.signLabel)
      put(opts.signLabel, f0.localToWorld(v3.set(1.9, 4.4, D + 1.6)), 18, -18, rec > 0.6);
  };
  raf = requestAnimationFrame(frame);

  return {
    setVisible(v: boolean) {
      visible = v;
    },
    setProgress(q: number) {
      if (!reduced) st.pT = clamp(q, 0, 1);
    },
    dispose() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      cv.removeEventListener("pointerdown", down);
      cv.removeEventListener("pointermove", move);
      cv.removeEventListener("pointerup", up);
      cv.removeEventListener("pointercancel", up);
      cv.removeEventListener("pointerleave", leave);
      scene.traverse((n) => {
        if (!(n instanceof THREE.Mesh || n instanceof THREE.Points)) return;
        n.geometry.dispose();
        const m: THREE.Material | THREE.Material[] = n.material;
        (Array.isArray(m) ? m : [m]).forEach((x) => {
          if ("map" in x && x.map instanceof THREE.Texture) x.map.dispose();
          x.dispose();
        });
      });
      R.dispose();
    },
  };
}
