// The drawing behind the one box: a front elevation of a made-up four-storey walk-up, drafted
// in thin lines the way a building record is. It is a drawing, never a photograph and never a
// real address. Three numbered marks tie it to the three steps listed beside it: the ad arrives
// at the door (01), the building is measured against its record (02), the report comes back
// (03). A few windows brighten and dim slowly; with reduced motion they hold still (onebox.css).

const FLOORS = [104, 169, 234] as const;
const BAYS = [144, 208, 272, 336] as const;
/** Windows that are "home": floor index, bay index, and where in the slow cycle each starts. */
const LIT: Record<string, number> = { "0-3": 0, "1-1": 2.4, "2-2": 4.8, "0-0": 6.1, "2-0": 3.3 };

function Mark({ n, x, y }: { n: string; x: number; y: number }) {
  return (
    <g className="el-mark">
      <rect x={x - 12} y={y - 10} width="24" height="20" />
      <text x={x} y={y + 3.5} textAnchor="middle">
        {n}
      </text>
    </g>
  );
}

export function Elevation() {
  return (
    <svg
      className="el"
      viewBox="0 0 520 400"
      role="presentation"
      aria-hidden="true"
      focusable="false"
      data-testid="ob-elevation"
    >
      {/* The lot: ground line and the lower building next door. */}
      <path className="el-thin" d="M0 352H520" />
      <path className="el-thin" d="M400 236H478V352M400 248H478" />
      {[258, 304].map((y) =>
        [416, 446].map((x) => (
          <rect key={`${x}-${y}`} className="el-pane" x={x} y={y} width="18" height="26" />
        )),
      )}

      {/* The building: wall, cornice, floor lines. */}
      <path className="el-wall el-draw" pathLength={1} d="M120 352V92H400V352" />
      <path
        className="el-wall el-draw"
        pathLength={1}
        d="M110 92H410M114 84H406M114 84V92M406 84V92"
      />
      <path className="el-thin" d="M120 157H400M120 222H400M120 287H400" />

      {/* Three floors of windows, four bays. */}
      {FLOORS.map((y, f) =>
        BAYS.map((x, b) => {
          const lit = LIT[`${f}-${b}`];
          return (
            <g key={`${f}-${b}`}>
              <rect
                className={lit === undefined ? "el-pane" : "el-pane el-lit"}
                style={lit === undefined ? undefined : { animationDelay: `-${lit}s` }}
                x={x}
                y={y}
                width="40"
                height="44"
              />
              <path className="el-hair" d={`M${x + 20} ${y}V${y + 44}M${x} ${y + 22}H${x + 40}`} />
              <path className="el-thin" d={`M${x - 4} ${y + 44}H${x + 44}`} />
            </g>
          );
        }),
      )}

      {/* Street level: two shopfronts, the door, its transom and two steps. */}
      <rect className="el-pane" x="144" y="302" width="76" height="38" />
      <rect className="el-pane" x="300" y="302" width="76" height="38" />
      <path className="el-wall" d="M244 352V300H276V352M244 314H276" />
      <path className="el-thin" d="M260 314V352M236 352V346H284V352" />

      {/* Dimension lines, as on a record drawing. */}
      <path className="el-dim" d="M120 60H400M120 54V66M400 54V66M213 54V66M307 54V66" />
      <path
        className="el-dim"
        d="M498 92V352M492 92H504M492 352H504M492 157H504M492 222H504M492 287H504"
      />

      {/* The three steps, marked where they happen. */}
      <path className="el-lead" d="M260 352V374" />
      <Mark n="01" x={260} y={384} />
      <path className="el-lead" d="M76 190H120" />
      <Mark n="02" x={64} y={190} />
      <path className="el-lead" d="M376 126H436V112" />
      <Mark n="03" x={436} y={102} />
    </svg>
  );
}
