// One plain line per stop: what you are looking at, in the renter's words. Built only from the
// plan's own fields, so it can never say more than the walk knows.
import type { TourPlan, TourStop } from "../contracts";

export function seeingLine(stop: TourStop, plan: TourPlan, realView: boolean): string {
  const view = realView ? "the real 3D scan" : "a drawing of this kind of room";
  if (stop.kind === "arrive")
    return "You are outside. This is where the walk starts, before you go in.";
  if (stop.kind === "outro") return "That is the whole walk. Next, see the place in person.";
  const room = stop.room_label ?? stop.title;
  const where =
    stop.kind === "door" ? "You are at the front door" : `You are in the ${room.toLowerCase()}`;
  if (stop.photos.length > 0)
    return `${where}, looking at ${view}. A photo from the ad was taken here, and it is shown where it was taken.`;
  if (stop.ad_view === "none_placed")
    return `${where}, looking at ${view}. The ad showed no photo of this room, so look closely.`;
  return `${where}, looking at ${view}.${plan.rooms_labelled ? "" : " Rooms in this scan are not named."}`;
}

/** Where to go from the walk: back to the result or the place, and to check an ad. */
export function waysOut(plan: TourPlan, caseId: string | null | undefined) {
  const back = caseId
    ? { href: `/case/${encodeURIComponent(caseId)}`, label: "Back to your result" }
    : {
        href: `/map?place=${encodeURIComponent(plan.property_id)}`,
        label: "Back to this place on the map",
      };
  return { back, check: { href: "/home#listing", label: "Check an ad" } };
}
