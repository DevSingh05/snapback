import type { Item } from "../home/OneBox";
import type { Intent } from "../home/intent";

// The lines of a story's thread, in the shapes the Home thread draws.

type Shown = Exclude<Item, { type: "check" | "places" }>;
export type ThreadEntry = Shown extends infer T ? (T extends Shown ? Omit<T, "id"> : never) : never;

let ids = 1;
export const withId = (e: ThreadEntry) => ({ ...e, id: ids++ }) as Item;

export const you = (text: string, files: string[] = []): ThreadEntry => ({
  type: "you",
  text,
  files,
});
export const routed = (kind: Intent["kind"]): ThreadEntry =>
  ({ type: "route", intent: { kind }, sub: null }) as ThreadEntry;
export const bot = (text: string, by: "model" | "policy" = "policy"): ThreadEntry => ({
  type: "bot",
  text,
  by,
});
