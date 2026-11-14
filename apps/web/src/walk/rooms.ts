// The stand-in rooms, one per room kind, each a list of parts drawn far to near. They are
// generic drawings of a kind of room, never this home's real layout, and the stage says so.
// The left wall between y 60 and 180 stays clear above z 60: that is where the ad photo lands.
import type { TourStop } from "../contracts";
import {
  armchair,
  bed,
  cabinetsLeft,
  cabinetsRight,
  closetLeft,
  coffeeTable,
  doorRight,
  floorLamp,
  fridgeRight,
  hallBench,
  island,
  mirrorRight,
  nightstand,
  plant,
  rangeRight,
  rug,
  shell,
  sideboardRight,
  sinkRight,
  sofa,
  toilet,
  tubLeft,
  tvUnitLeft,
  upperRight,
  wallTile,
  windowRight,
  type Part,
} from "./roomParts";

export type RoomKind = "kitchen" | "bathroom" | "bedroom" | "living" | "entry" | "plain";

export function roomKind(stop: TourStop): RoomKind {
  const name = `${stop.room_label ?? ""} ${stop.title}`.toLowerCase();
  if (name.includes("kitchen")) return "kitchen";
  if (name.includes("bath")) return "bathroom";
  if (name.includes("bed")) return "bedroom";
  if (name.includes("living") || name.includes("family") || name.includes("lounge"))
    return "living";
  if (stop.kind === "door" || name.includes("entry") || name.includes("hall")) return "entry";
  return "plain";
}

export interface RoomDrawing {
  /** Floor, walls, openings, rugs and light: everything the camera cone is drawn over. */
  base: Part[];
  /** Furniture and fixtures, far to near: drawn over the cone. */
  things: Part[];
}

const ROOMS: Record<RoomKind, () => RoomDrawing> = {
  kitchen: () => ({
    base: [...shell("tile"), ...windowRight(154, 208, 84, 130)],
    things: [
      ...upperRight(30, 92, 2),
      ...cabinetsRight(30, 96, { doors: 2 }),
      ...rangeRight(96),
      ...cabinetsRight(146, 220, { doors: 2 }),
      ...sinkRight(182),
      ...fridgeRight(224),
      ...cabinetsLeft(66, 216, { doors: 4 }),
      ...island(128, 142, 110, 48),
    ],
  }),
  bathroom: () => ({
    base: [
      ...shell("tile"),
      ...wallTile(80),
      ...windowRight(232, 284, 92, 132),
      rug(96, 74, 96, 58),
    ],
    things: [
      mirrorRight(120, 196, 76, 132),
      ...cabinetsRight(110, 206, { doors: 2, d: 40, tone: "wood" }),
      ...sinkRight(158, 56, 40),
      ...toilet(238),
      ...tubLeft(40, 216),
    ],
  }),
  bedroom: () => ({
    base: [...shell("planks"), ...windowRight(238, 288, 70, 132), rug(40, 150, 220, 110)],
    things: [...nightstand(26), ...bed(70), ...nightstand(232), ...closetLeft(198, 288)],
  }),
  living: () => ({
    base: [...shell("planks"), ...windowRight(84, 196, 88, 136), rug(70, 96, 160, 120)],
    things: [
      ...floorLamp(22, 18),
      ...sofa(48),
      ...plant(252, 6),
      ...coffeeTable(104, 122),
      ...tvUnitLeft(196, 286),
    ],
  }),
  entry: () => ({
    base: [
      ...shell("planks"),
      ...doorRight(96, 156, 124),
      ...windowRight(22, 62, 60, 130),
      rug(84, 26, 86, 60),
    ],
    things: [
      ...hallBench(186, 280),
      ...cabinetsLeft(70, 170, { doors: 2, d: 30, h: 52, tone: "wood" }),
      ...plant(6, 232),
    ],
  }),
  plain: () => ({
    base: [...shell("planks"), ...windowRight(150, 250, 76, 134), rug(96, 110, 150, 110)],
    things: [...sideboardRight(30, 130), ...armchair(206, 60), ...plant(6, 236)],
  }),
};

export const drawRoom = (kind: RoomKind): RoomDrawing => ROOMS[kind]();
