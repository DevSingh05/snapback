// "Taken here": one floor of a scanned home, cut open, drawn with three.js. A sample photo from
// "the ad" flies in from its thumbnail, a view cone grows from where the camera stood, corner
// marks lock onto the wall the photo shows, and matched points join the photo to the wall. A
// photo from another home tries each room and is turned away. Ported from the SNAPBACK Worlds
// page (v17). Pure drawing: the home, the photos' poses and the counts are a sample.
import * as THREE from "three";

const PAL: Record<string, string> = {
  stone: "#D8CFC0",
  wall: "#FBFAF7",
  floor: "#CDAE86",
  glass: "#B4D3E6",
  dark: "#3A4A54",
  act: "#3FB6C2",
  scan: "#DFA20A",
  mu: "#8FA0A8",
  ink: "#161A1B",
  bad: "#FFB9A0",
  x: "#E2603A",
};

const PIT = 0.528;
const CD = 150;
const F = 0.46;
const N = 28;
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const back = (t: number) => {
  const u = clamp(t, 0, 1) - 1;
  return 1 + 2.4 * u * u * u + 1.4 * u * u;
};
type V3 = [number, number, number];

export interface TwinCase {
  src: string;
  /** false: the photo is from another home, and no room takes it. */
  fits: boolean;
  /** centre of the wall area the photo shows, and the spot the camera stood (floor units) */
  C?: readonly [number, number, number];
  A?: readonly [number, number, number];
  w?: number;
  h?: number;
  ry?: number;
  /** matched points in this drawn sample */
  n?: number;
}

export interface TwinScene {
  setVisible(v: boolean): void;
  /** Fly photo i in from a rectangle on the page (its thumbnail). done fires when it settles. */
  play(i: number, from: DOMRect | null, done: () => void): void;
  dispose(): void;
}

export interface TwinLabels {
  cam: HTMLElement | null;
  wall: HTMLElement | null;
  count: HTMLElement | null;
}

export function mountTwin(
  cv: HTMLCanvasElement,
  el: HTMLElement,
  reduced: boolean,
  cases: readonly TwinCase[],
  labels: TwinLabels,
): TwinScene | null {
  let R: THREE.WebGLRenderer;
  try {
    R = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
  } catch {
    return null;
  }
  R.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  R.shadowMap.enabled = true;
  R.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene(),
    cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 440),
    rootG = new THREE.Group();
  scene.add(rootG);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xcedbe3, 0.66));
  const sun = new THREE.DirectionalLight(0xffffff, 0.45);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.bias = -0.0008;
  sun.shadow.radius = 3;
  const sc = sun.shadow.camera;
  sc.left = sc.bottom = -14;
  sc.right = sc.top = 14;
  sc.near = 1;
  sc.far = 90;
  sun.position.set(9, 30, 17.8);
  scene.add(sun);
  scene.add(sun.target);
  const col = (t: string) => new THREE.Color(PAL[t] ?? "#ffffff");
  const M = (t: string, o?: THREE.MeshStandardMaterialParameters) =>
    new THREE.MeshStandardMaterial(
      Object.assign({ roughness: 0.94, metalness: 0, color: col(t) }, o || {}),
    );
  const B = (t: string, o?: THREE.MeshBasicMaterialParameters) =>
    new THREE.MeshBasicMaterial(
      Object.assign({ transparent: true, depthWrite: false, color: col(t) }, o || {}),
    );
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

  const U = new THREE.Group();
  U.position.set(-4.5, 0, -3);
  rootG.add(U);
  const mStone = M("stone"),
    mWall = M("wall"),
    mFloor = M("floor"),
    mDark = M("dark");
  box(U, 9.8, 0.3, 6.8, -0.4, -0.3, -0.4, mStone);
  box(U, 9, 0.04, 6, 0, 0, 0, mFloor, false).receiveShadow = true;
  // survey ticks along two edges of the slab
  for (let n = 0; n <= 9; n++)
    box(U, 0.03, 0.012, n % 3 ? 0.14 : 0.3, n - 0.015, 0, 6.08, mDark, false);
  for (let n = 0; n <= 6; n++)
    box(U, n % 3 ? 0.14 : 0.3, 0.012, 0.03, 9.08, 0, n - 0.015, mDark, false);
  // four outer walls; each fades when it comes between the viewer and the room
  type Wall = {
    g: THREE.Group;
    n: [number, number];
    mats: THREE.Material[];
    o: number;
    wl: THREE.Material;
    st: THREE.Material;
    dk: THREE.Material;
    gl: THREE.Material;
  };
  const walls: Wall[] = [];
  const wall = (n: [number, number]): Wall => {
    const g = new THREE.Group();
    U.add(g);
    const wl = M("wall", { transparent: true }),
      st = M("stone", { transparent: true }),
      dk = M("dark", { transparent: true }),
      gl = new THREE.MeshStandardMaterial({
        transparent: true,
        roughness: 0.2,
        color: col("glass"),
        emissive: col("glass"),
        emissiveIntensity: 0.12,
      });
    const w = { g, n, mats: [wl, st, dk, gl], o: n[0] + n[1] < 0 ? 1 : 0, wl, st, dk, gl };
    walls.push(w);
    return w;
  };
  const wx0 = wall([-1, 0]),
    wz0 = wall([0, -1]),
    wx9 = wall([1, 0]),
    wz6 = wall([0, 1]);
  box(U, 0.2, 0.22, 6.4, -0.2, 0, -0.2, mWall);
  box(U, 9.4, 0.22, 0.2, -0.2, 0, -0.2, mWall);
  box(U, 0.2, 0.22, 6.4, 9, 0, -0.2, mWall);
  box(U, 9.4, 0.22, 0.2, -0.2, 0, 6, mWall);
  box(wx0.g, 0.2, 2.38, 6.4, -0.2, 0.22, -0.2, wx0.wl);
  box(wx0.g, 0.07, 2.1, 1.08, 0, 0, 0.4, wx0.st, false);
  box(wx0.g, 0.07, 2.1, 1.08, 0, 0, 1.52, wx0.st, false);
  box(wx0.g, 0.36, 0.7, 2.5, 0, 1.5, 3.3, wx0.st);
  box(wz0.g, 9.4, 2.38, 0.2, -0.2, 0.22, -0.2, wz0.wl);
  box(wz0.g, 3.9, 2.0, 0.05, 4.35, 0.3, 0, wz0.gl, false);
  [4.35, 5.3, 6.25, 7.2, 8.19].forEach((x) =>
    box(wz0.g, 0.06, 2.0, 0.08, x, 0.3, 0, wz0.dk, false),
  );
  box(wz0.g, 3.9, 0.06, 0.08, 4.35, 1.55, 0, wz0.dk, false);
  box(wz0.g, 3.9, 0.06, 0.08, 4.35, 2.26, 0, wz0.dk, false);
  box(wz0.g, 1.0, 1.4, 0.05, 1.25, 0.8, 0, wz0.gl, false);
  box(wx9.g, 0.2, 2.38, 6.4, 9, 0.22, -0.2, wx9.wl);
  box(wx9.g, 0.06, 2.05, 0.95, 8.95, 0, 3.4, wx9.dk, false);
  box(wz6.g, 9.4, 2.38, 0.2, -0.2, 0.22, 6, wz6.wl);
  box(wz6.g, 1.1, 1.1, 0.05, 1.2, 1.0, 5.95, wz6.gl, false);
  // kitchen and inner half walls, a sofa and a rug so the rooms read
  box(U, 0.6, 0.86, 2.5, 0, 0, 3.3, mStone);
  box(U, 0.64, 0.05, 2.54, 0, 0.86, 3.28, mWall);
  box(U, 0.62, 1.8, 0.62, 0, 0, 5.34, mDark);
  box(U, 0.12, 0.9, 2.2, 3.4, 0, 0, mWall);
  box(U, 0.12, 0.9, 2.8, 3.4, 0, 3.2, mWall);
  box(U, 3.4, 0.9, 0.12, 0, 0, 3, mWall);
  const mSofa = M("dark", { color: new THREE.Color("#6E8597") });
  box(
    U,
    2.4,
    0.02,
    1.7,
    5.1,
    0.04,
    1.6,
    M("wall", { color: new THREE.Color("#E6D9C6") }),
    false,
  ).receiveShadow = true;
  box(U, 2.2, 0.42, 0.85, 5.2, 0.04, 3.5, mSofa);
  box(U, 2.2, 0.5, 0.22, 5.2, 0.46, 4.13, mSofa);
  box(U, 1.5, 0.4, 2.0, 1.0, 0.04, 0.5, mWall);
  box(U, 1.5, 0.14, 1.2, 1.0, 0.44, 1.3, mSofa);
  // the scan points on the floor and far walls
  {
    const p: number[] = [],
      s = 0.24,
      o = 0.03;
    for (let x = s / 2; x < 9; x += s) for (let z = s / 2; z < 6; z += s) p.push(x, o + 0.04, z);
    for (let y = s / 2; y < 2.55; y += s) {
      for (let z = s / 2; z < 6; z += s) p.push(o, y, z);
      for (let x = s / 2; x < 9; x += s) p.push(x, y, o);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(p), 3));
    const P = new THREE.Points(
      g,
      new THREE.PointsMaterial({
        size: 1.7 * R.getPixelRatio(),
        sizeAttenuation: false,
        transparent: true,
        opacity: 0.4,
        depthWrite: false,
        color: col("scan"),
      }),
    );
    P.frustumCulled = false;
    U.add(P);
  }
  // the photo
  const TL = new THREE.TextureLoader(),
    tex = cases.map((c) => TL.load(c.src));
  const P = new THREE.Group();
  U.add(P);
  P.visible = false;
  const bm = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: 2,
      polygonOffsetUnits: 2,
    }),
    im = new THREE.MeshBasicMaterial({ map: tex[0] ?? null });
  P.add(new THREE.Mesh(new THREE.PlaneGeometry(1.06, 1.09), bm));
  const ipl = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), im);
  ipl.position.z = 0.012;
  P.add(ipl);
  const cW = new THREE.Color(0xffffff),
    cBad = col("bad"),
    cScan = col("scan"),
    cAct = col("act"),
    cX = col("x");
  // view cone: built once per photo in the frame of the camera spot, then only scaled
  const CG = new THREE.Group();
  U.add(CG);
  const mRod = B("act", { opacity: 0.95, depthWrite: true }),
    rods = [0, 1, 2, 3].map(() => {
      const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mRod);
      CG.add(m);
      return m;
    });
  const fg = new THREE.BufferGeometry(),
    fp = new Float32Array(36);
  fg.setAttribute("position", new THREE.BufferAttribute(fp, 3));
  const faces = new THREE.Mesh(fg, B("act", { opacity: 0.09, side: THREE.DoubleSide }));
  faces.frustumCulled = false;
  faces.renderOrder = 2;
  CG.add(faces);
  const gg = new THREE.BufferGeometry(),
    gp = new Float32Array(9);
  gg.setAttribute("position", new THREE.BufferAttribute(gp, 3));
  const foot = new THREE.Mesh(
    gg,
    B("scan", {
      opacity: 0.3,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -4,
      polygonOffsetUnits: -4,
    }),
  );
  foot.frustumCulled = false;
  CG.add(foot);
  const CM = new THREE.Group();
  U.add(CM);
  const mCam = M("ink");
  box(CM, 0.4, 0.28, 0.3, -0.2, -0.14, -0.2, mCam);
  box(CM, 0.2, 0.2, 0.14, -0.1, -0.1, 0.1, mCam);
  box(CM, 0.05, 1.5, 0.05, -0.025, -1.6, -0.07, mCam);
  // viewfinder corners on the wall the photo shows
  const BR = new THREE.Group();
  U.add(BR);
  const mBr = new THREE.MeshBasicMaterial({ transparent: true, depthTest: false });
  const brs: THREE.Mesh[] = [];
  for (let n = 0; n < 8; n++) {
    const m = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 0.02), mBr);
    m.renderOrder = 4;
    BR.add(m);
    brs.push(m);
  }
  // matched points: a dot on the photo, a dot on the wall, a line between
  const FP: [number, number][] = [];
  let sd = 7;
  const rn = () => {
    sd = (sd * 16807) % 2147483647;
    return sd / 2147483647;
  };
  for (let n = 0; n < N; n++) FP.push([rn() * 0.86 - 0.43, rn() * 0.82 - 0.41]);
  const la = new Float32Array(N * 6),
    lg = new THREE.BufferGeometry();
  lg.setAttribute("position", new THREE.BufferAttribute(la, 3));
  const lines = new THREE.LineSegments(
    lg,
    new THREE.LineBasicMaterial({
      transparent: true,
      opacity: 0.75,
      depthTest: false,
      color: col("scan"),
    }),
  );
  lines.frustumCulled = false;
  lines.renderOrder = 5;
  U.add(lines);
  const dg = new THREE.BufferGeometry();
  dg.setAttribute("position", new THREE.BufferAttribute(la, 3));
  const mDot = new THREE.PointsMaterial({
    size: 5,
    sizeAttenuation: false,
    transparent: true,
    depthTest: false,
    color: col("scan"),
  });
  const dots = new THREE.Points(dg, mDot);
  dots.frustumCulled = false;
  dots.renderOrder = 6;
  U.add(dots);

  const p0 = new THREE.Vector3(),
    p1 = new THREE.Vector3(),
    q0 = new THREE.Quaternion(),
    q1 = new THREE.Quaternion(),
    qa = new THREE.Quaternion(),
    Z = new THREE.Vector3(0, 0, 1),
    Y = new THREE.Vector3(0, 1, 0),
    d3 = new THREE.Vector3(),
    pos = new THREE.Vector3(),
    v = new THREE.Vector3();
  let face = false,
    w0 = 1,
    h0 = 1,
    w1 = 1,
    h1 = 1,
    ppuNow = 50,
    dim = { cw: 1, ch: 1 },
    cur: TwinCase | null = null;
  const tv = { s: 0, g: 0, br: 0, mp: 0, fl: 0, pop: 0, tint: 0, vis: 0 };
  const ob = { yaw: 0, yawT: 0, pit: PIT, pitT: PIT, idle: 0 };

  function setCase(c: TwinCase, keep?: boolean) {
    const C = c.C,
      A = c.A;
    if (!C || !A) return;
    const ry = c.ry ?? 0,
      cw = c.w ?? 2.4,
      chh = c.h ?? 1.6,
      r: V3 = [Math.cos(ry), 0, -Math.sin(ry)],
      hw = cw / 2,
      hh = chh / 2;
    cur = c;
    const SG: [number, number][] = [
      [-1, 1],
      [1, 1],
      [1, -1],
      [-1, -1],
    ];
    const q: V3[] = SG.map((s) => [
      C[0] + r[0] * hw * s[0] - A[0],
      C[1] + hh * s[1] - A[1],
      C[2] + r[2] * hw * s[0] - A[2],
    ]);
    CG.position.set(A[0], A[1], A[2]);
    q.forEach((c2, n) => {
      const rod = rods[n],
        nx = q[(n + 1) % 4];
      if (!rod || !nx) return;
      d3.set(c2[0], c2[1], c2[2]);
      const len = d3.length();
      rod.position.copy(d3).multiplyScalar(0.5);
      rod.quaternion.setFromUnitVectors(Z, d3.normalize());
      rod.scale.set(0.028, 0.028, len);
      fp.set([0, 0, 0], n * 9);
      fp.set(c2, n * 9 + 3);
      fp.set(nx, n * 9 + 6);
    });
    const q2 = q[2],
      q3 = q[3];
    if (q2 && q3) gp.set([0, 0.07 - A[1], 0, q2[0], 0.07 - A[1], q2[2], q3[0], 0.07 - A[1], q3[2]]);
    const fa = fg.getAttribute("position") as THREE.BufferAttribute,
      ga = gg.getAttribute("position") as THREE.BufferAttribute;
    fa.needsUpdate = ga.needsUpdate = true;
    fg.computeBoundingSphere();
    CM.position.set(A[0], A[1], A[2]);
    CM.rotation.y = Math.atan2(C[0] - A[0], C[2] - A[2]);
    BR.position.set(C[0], C[1], C[2]);
    BR.rotation.y = ry;
    const bl = Math.min(cw, chh) * 0.2,
      t = 0.07;
    SG.forEach((s, n) => {
      const a = brs[n * 2],
        b = brs[n * 2 + 1];
      if (!a || !b) return;
      a.scale.set(bl, t, 1);
      a.position.set(s[0] * (hw - bl / 2), s[1] * hh, 0);
      b.scale.set(t, bl, 1);
      b.position.set(s[0] * hw, s[1] * (hh - bl / 2), 0);
    });
    FP.forEach((f, n) => {
      const wq: V3 = [C[0] + r[0] * f[0] * cw, C[1] + f[1] * chh, C[2] + r[2] * f[0] * cw];
      la.set(
        [A[0] + (wq[0] - A[0]) * F, A[1] + (wq[1] - A[1]) * F, A[2] + (wq[2] - A[2]) * F],
        n * 6,
      );
      la.set(wq, n * 6 + 3);
    });
    (lg.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
    (dg.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
    if (keep) return;
    face = false;
    p1.set(A[0] + (C[0] - A[0]) * F, A[1] + (C[1] - A[1]) * F, A[2] + (C[2] - A[2]) * F);
    q1.setFromAxisAngle(Y, ry);
    w1 = cw * F;
    h1 = chh * F;
  }
  const frameCam = () => {
    const cw = dim.cw,
      ch = dim.ch;
    ppuNow = Math.min(58, cw / 13.2, ch / 9.6);
    const c = cam,
      cx = cw / 2,
      cy = ch * 0.56;
    c.left = -cx / ppuNow;
    c.right = (cw - cx) / ppuNow;
    c.top = cy / ppuNow;
    c.bottom = c.top - ch / ppuNow;
    const cp = Math.cos(ob.pit) * CD * 0.7071;
    c.position.set(cp, Math.sin(ob.pit) * CD + 0.9, cp);
    c.lookAt(0, 0.9, 0);
    c.updateProjectionMatrix();
    c.updateMatrixWorld();
    mDot.size = clamp(ppuNow * 0.09, 3, 6) * R.getPixelRatio();
  };
  const size = () => {
    dim = { cw: el.clientWidth || 1, ch: el.clientHeight || 1 };
    R.setSize(dim.cw, dim.ch, false);
    frameCam();
  };
  const ro = new ResizeObserver(size);
  ro.observe(el);
  size();

  // tweens: a handful of numbers eased over time
  type Tw = {
    props: Partial<typeof tv>;
    from: Partial<typeof tv> | null;
    t0: number;
    ms: number;
    fn?: () => void;
  };
  let tw: Tw[] = [],
    timers: number[] = [];
  const go = (props: Partial<typeof tv>, ms: number, delay = 0, fn?: () => void) => {
    if (reduced) {
      Object.assign(tv, props);
      fn?.();
      return;
    }
    tw.push({ props, from: null, t0: performance.now() + delay, ms, fn });
  };
  const stepTw = (now: number) => {
    const done: (() => void)[] = [];
    tw = tw.filter((t) => {
      if (now < t.t0) return true;
      const keys = Object.keys(t.props) as (keyof typeof tv)[];
      if (!t.from) {
        t.from = {};
        for (const k of keys) t.from[k] = tv[k];
      }
      const p = Math.min(1, (now - t.t0) / t.ms),
        e = 1 - Math.pow(1 - p, 3);
      for (const k of keys) {
        const a = t.from[k] ?? 0,
          b = t.props[k] ?? 0;
        tv[k] = a + (b - a) * e;
      }
      if (p >= 1) {
        if (t.fn) done.push(t.fn);
        return false;
      }
      return true;
    });
    done.forEach((f) => f());
  };

  const pts = new Map<number, [number, number]>();
  const down = (e: PointerEvent) => {
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    cv.setPointerCapture(e.pointerId);
    cv.classList.add("drag");
  };
  const move = (e: PointerEvent) => {
    const p = pts.get(e.pointerId);
    if (!p) return;
    ob.yawT += (e.clientX - p[0]) * 0.008;
    if (e.pointerType !== "touch") ob.pitT = clamp(ob.pitT + (e.clientY - p[1]) * 0.005, 0.25, 1.2);
    pts.set(e.pointerId, [e.clientX, e.clientY]);
    ob.idle = performance.now();
  };
  const up = (e: PointerEvent) => {
    pts.delete(e.pointerId);
    if (!pts.size) cv.classList.remove("drag");
    ob.idle = performance.now();
  };
  cv.addEventListener("pointerdown", down);
  cv.addEventListener("pointermove", move);
  cv.addEventListener("pointerup", up);
  cv.addEventListener("pointercancel", up);

  const lst = new Map<HTMLElement, string>();
  const put = (n: HTMLElement | null, x: V3 | null, dy: number, show: boolean) => {
    if (!n) return;
    if (x) {
      U.localToWorld(v.set(x[0], x[1], x[2])).project(cam);
      const px = clamp(((v.x + 1) / 2) * dim.cw, 70, dim.cw - 70),
        py = clamp(((1 - v.y) / 2) * dim.ch + dy, 6, dim.ch - 34);
      n.style.transform = `translate3d(${px.toFixed(1)}px,${py.toFixed(1)}px,0) translateX(-50%)`;
    }
    const o = show && x ? "1" : "0";
    if (lst.get(n) !== o) {
      lst.set(n, o);
      n.style.opacity = o;
    }
  };

  let visible = true,
    raf = 0,
    lastN = -1;
  const frame = (now: number) => {
    raf = requestAnimationFrame(frame);
    if (!visible) return;
    stepTw(now);
    if (!reduced && !pts.size && now - ob.idle > 4000) {
      const base = Math.round(ob.yawT / (Math.PI * 2)) * Math.PI * 2;
      ob.yawT += (base + 0.22 * Math.sin(now * 0.0002) - ob.yawT) * 0.012;
      ob.pitT += (PIT - ob.pitT) * 0.012;
    }
    const k = reduced ? 1 : 0.11;
    ob.yaw += (ob.yawT - ob.yaw) * k;
    ob.pit += (ob.pitT - ob.pit) * k;
    rootG.rotation.y = ob.yaw;
    frameCam();
    const cx = 0.7071 * (Math.cos(ob.yaw) - Math.sin(ob.yaw)),
      cz = 0.7071 * (Math.sin(ob.yaw) + Math.cos(ob.yaw));
    walls.forEach((w) => {
      const t = clamp(0.5 - (w.n[0] * cx + w.n[1] * cz) / 0.3, 0, 1);
      w.o += (t - w.o) * (reduced ? 1 : 0.14);
      w.mats.forEach((m) => (m.opacity = w.o));
      w.g.visible = w.o > 0.02;
    });
    rootG.updateMatrixWorld(true);
    U.getWorldQuaternion(qa);
    q0.copy(qa).invert().multiply(cam.quaternion);
    if (face) q1.copy(q0);
    const e = tv.s;
    pos.lerpVectors(p0, p1, e);
    pos.y += Math.sin(Math.PI * e) * 1.1;
    P.position.copy(pos);
    P.quaternion.copy(q0).slerp(q1, e);
    const pop = 1 + Math.sin(tv.pop * Math.PI) * 0.1;
    P.scale.set((w0 + (w1 - w0) * e) * pop, (h0 + (h1 - h0) * e) * pop, 1);
    P.visible = tv.vis > 0.5;
    bm.color.copy(cW).lerp(cScan, tv.fl).lerp(cBad, tv.tint);
    const g = tv.g;
    CG.visible = g > 0.01;
    CG.scale.setScalar(Math.max(0.001, g));
    CM.visible = g > 0.5;
    CM.scale.setScalar(back((g - 0.5) / 0.5));
    BR.visible = tv.br > 0.02;
    BR.scale.setScalar(1 + (1 - back(tv.br)) * 0.45);
    mBr.opacity = Math.min(1, tv.br * 1.5);
    mBr.color.copy(cAct).lerp(cX, tv.tint);
    const nn = Math.round(N * tv.mp);
    lg.setDrawRange(0, nn * 2);
    dg.setDrawRange(0, nn * 2);
    lines.visible = dots.visible = nn > 0;
    const fits = !!cur && cur.fits && tv.tint === 0,
      num = fits ? Math.round((cur?.n ?? 0) * tv.mp) : 0;
    if (num !== lastN && labels.count) labels.count.textContent = String((lastN = num));
    R.render(scene, cam);
    const A = cur?.A,
      C = cur?.C;
    put(labels.cam, A ? [A[0], 0, A[2]] : null, 10, fits && g > 0.95);
    put(
      labels.wall,
      C ? [C[0], C[1] + (cur?.h ?? 1.6) / 2 + 0.2, C[2]] : null,
      -38,
      fits && tv.br > 0.6,
    );
  };
  raf = requestAnimationFrame(frame);

  const stop = () => {
    timers.forEach((t) => window.clearTimeout(t));
    timers = [];
    tw = [];
  };

  return {
    setVisible(x: boolean) {
      visible = x;
    },
    play(i: number, from: DOMRect | null, done: () => void) {
      const c = cases[i];
      if (!c) return;
      stop();
      Object.assign(tv, { s: 0, g: 0, br: 0, mp: 0, fl: 0, pop: 0, tint: 0, vis: 1 });
      im.map = tex[i] ?? null;
      im.needsUpdate = true;
      // where the thumbnail sits, in the floor's own space, facing the viewer
      const r = cv.getBoundingClientRect(),
        b = from ?? new DOMRect(r.left + r.width * 0.1, r.bottom - 80, 96, 72);
      rootG.updateMatrixWorld(true);
      p0.set(
        ((b.left + b.width / 2 - r.left) / r.width) * 2 - 1,
        -(((b.top + b.height / 2 - r.top) / r.height) * 2 - 1),
        -0.7,
      ).unproject(cam);
      U.worldToLocal(p0);
      w0 = b.width / ppuNow;
      h0 = b.height / ppuNow;
      const fitters = cases.filter((x) => x.fits);
      if (c.fits) {
        setCase(c);
        if (reduced) {
          Object.assign(tv, { s: 1, g: 1, br: 1, mp: 1 });
          done();
          return;
        }
        go({ s: 1 }, 900, 0, () => {
          tv.fl = tv.pop = 1;
          go({ fl: 0, pop: 0 }, 420);
          go({ g: 1 }, 620, 60, () => {
            go({ br: 1 }, 420);
            go({ mp: 1 }, 1400, 160, done);
          });
        });
        return;
      }
      // another home's photo: it hovers, tries each room's wall, reddens and is turned away
      cur = c;
      if (reduced) {
        tv.vis = 0;
        done();
        return;
      }
      face = true;
      p1.set(4.5, 4.3, 3);
      w1 = 2.7;
      h1 = 1.8;
      go({ s: 1 }, 800);
      fitters.forEach((fc, j) =>
        timers.push(
          window.setTimeout(
            () => {
              setCase(fc, true);
              cur = c;
              tv.br = 0;
              go({ br: 1, tint: (j + 1) / fitters.length }, 380);
            },
            860 + j * 640,
          ),
        ),
      );
      timers.push(
        window.setTimeout(
          () => {
            go({ br: 0 }, 250);
            go({ s: 0 }, 650, 200, () => {
              tv.vis = 0;
              done();
            });
          },
          860 + fitters.length * 640,
        ),
      );
    },
    dispose() {
      stop();
      cancelAnimationFrame(raf);
      ro.disconnect();
      cv.removeEventListener("pointerdown", down);
      cv.removeEventListener("pointermove", move);
      cv.removeEventListener("pointerup", up);
      cv.removeEventListener("pointercancel", up);
      tex.forEach((t) => t.dispose());
      scene.traverse((n) => {
        if (!(
          n instanceof THREE.Mesh ||
          n instanceof THREE.Points ||
          n instanceof THREE.LineSegments
        ))
          return;
        n.geometry.dispose();
        const m: THREE.Material | THREE.Material[] = n.material;
        (Array.isArray(m) ? m : [m]).forEach((x) => x.dispose());
      });
      R.dispose();
    },
  };
}
