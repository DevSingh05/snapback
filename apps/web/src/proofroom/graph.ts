// Where the check team's graph puts everyone. The Planner stands at the top, the members in
// rows of up to three, the Decider at the bottom. Lines run square, like the app's corners: a
// feed rail above each row carries work in from the Planner (lower rows are fed down the left
// edge), and a rail under each row carries findings out to the Decider (down the right edge).
// No line ever crosses a member. Pure numbers: the component draws them.
import { AVATAR } from "./Avatar";

export const COLS = 3;
export const EDGE = 5; // the trunks down each side sit this far in
const GUTTER = 16; // room each side for the trunks
const DROP = 14; // from a rail to the avatar under it
const TEXT = 62; // name (two lines held), role, state
export const NODE_H = AVATAR + TEXT;
const UNDER = 8; // from a member's last line to its out rail

export interface Spot {
  id: string;
  x: number; // centre
  y: number; // top of the avatar
  row: number;
}

export interface GraphLayout {
  width: number;
  height: number;
  colWidth: number;
  planner: Spot;
  decider: Spot;
  members: Spot[];
  // Path data from the Planner to a member, and from a member to the Decider.
  inPath: Record<string, string>;
  outPath: Record<string, string>;
}

const n = (v: number) => Math.round(v * 10) / 10;

export function graphLayout(
  width: number,
  plannerId: string,
  memberIds: readonly string[],
  deciderId: string,
): GraphLayout {
  const cx = n(width / 2);
  const cols = Math.max(1, Math.min(COLS, memberIds.length));
  const colWidth = n((width - 2 * GUTTER) / cols);
  const rows = Math.max(1, Math.ceil(memberIds.length / COLS));
  const feed = AVATAR + DROP; // the first rail, straight under the Planner
  const pitch = DROP + NODE_H + UNDER + DROP; // rail to rail
  const railIn = (row: number) => feed + row * pitch;
  const railOut = (row: number) => railIn(row) + DROP + NODE_H + UNDER;
  const collect = railOut(rows - 1);
  const deciderY = collect + DROP;
  const left = EDGE;
  const right = n(width - EDGE);

  const members: Spot[] = memberIds.map((id, i) => {
    const row = Math.floor(i / COLS);
    const inRow = Math.min(COLS, memberIds.length - row * COLS);
    const col = i - row * COLS;
    // A short row sits centred under the full ones.
    const start = cx - (inRow * colWidth) / 2;
    return { id, row, x: n(start + (col + 0.5) * colWidth), y: railIn(row) + DROP };
  });

  const inPath: Record<string, string> = {};
  const outPath: Record<string, string> = {};
  for (const m of members) {
    const top = m.y;
    const bottom = m.y + NODE_H;
    inPath[m.id] =
      m.row === 0
        ? `M${cx} ${AVATAR} V${feed} H${m.x} V${top}`
        : `M${cx} ${AVATAR} V${feed} H${left} V${railIn(m.row)} H${m.x} V${top}`;
    outPath[m.id] =
      m.row === rows - 1
        ? `M${m.x} ${bottom} V${collect} H${cx} V${deciderY}`
        : `M${m.x} ${bottom} V${railOut(m.row)} H${right} V${collect} H${cx} V${deciderY}`;
  }
  return {
    width,
    height: deciderY + AVATAR,
    colWidth,
    planner: { id: plannerId, x: cx, y: 0, row: -1 },
    decider: { id: deciderId, x: cx, y: deciderY, row: rows },
    members,
    inPath,
    outPath,
  };
}
