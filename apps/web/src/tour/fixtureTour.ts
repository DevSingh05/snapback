import type { TourPlan, TourStop } from "../contracts";

// Synthetic walkthrough for fixture mode and tests. Team-made, describes no real home. Its
// visuals are plain placeholder cards (see Placeholder in TourPage), never sponsor imagery.
const Q: [number, number, number, number] = [0, 0, 0, 1];

function stop(over: Partial<TourStop> & Pick<TourStop, "kind" | "key" | "title">): TourStop {
  return { sweep_count: 0, sweep_ids: [], photos: [], facts: [], ...over };
}

export const FIXTURE_TOUR: TourPlan = {
  property_id: "fixture-bldg-1",
  kind: "apartment",
  source: "fixture",
  as_of: "as of CoStar's last research",
  has_scan: true,
  scan_label: "a 3D scan in this building (it may be a model unit, not the one you'd rent)",
  rooms_labelled: true,
  rooms_note:
    "Room names are Matterport's automatic labels for each spot in the scan. They can be wrong, so look at the picture too.",
  aerial: { source: "fixture", captured_on: "2025-03-02", has_image: false },
  stops: [
    stop({
      kind: "arrive",
      key: "arrive",
      title: "Arrive outside",
      facts: [
        { text: "Built in 1998", source: "CoStar record" },
        { text: "12 floors", source: "CoStar record" },
        { text: "1.5 parking spaces per unit", source: "CoStar record" },
        { text: "Aerial photo captured Mar 2, 2025", source: "Vexcel aerial" },
      ],
      tip: "Look at the entrance, the lighting and the parking as you walk up.",
    }),
    stop({
      kind: "door",
      key: "door",
      title: "Front door",
      room_label: "Entryway",
      sweep_id: "fx-sweep-00",
      sweep_count: 1,
      sweep_ids: ["fx-sweep-00"],
      position: [0, 1.4, 0],
      rotation_quat: Q,
      facts: [{ text: "An elevator is on record", source: "CoStar record" }],
      tip: "Check the lock, and that the unit number on the door matches your lease.",
    }),
    stop({
      kind: "room",
      key: "room-2",
      title: "Living room",
      room_label: "Living room",
      sweep_id: "fx-sweep-01",
      sweep_count: 2,
      sweep_ids: ["fx-sweep-01", "fx-sweep-02"],
      position: [3, 1.4, 0],
      rotation_quat: Q,
      tip: "Turn on the AC and look at the vents; check the outlets and the street noise.",
    }),
    stop({
      kind: "room",
      key: "room-3",
      title: "Kitchen",
      room_label: "Kitchen",
      sweep_id: "fx-sweep-03",
      sweep_count: 1,
      sweep_ids: ["fx-sweep-03"],
      position: [8, 1.4, -2],
      rotation_quat: Q,
      photos: [{ photo_id: "photo-1", sweep_id: "fx-sweep-03" }],
      tip: "Open the fridge, oven and dishwasher: check every appliance listed is there and works.",
    }),
    stop({
      kind: "room",
      key: "room-4",
      title: "Bathroom",
      room_label: "Bathroom",
      sweep_id: "fx-sweep-06",
      sweep_count: 1,
      sweep_ids: ["fx-sweep-06"],
      position: [6, 1.4, 6],
      rotation_quat: Q,
      facts: [
        {
          text: "1 bathroom in this floor plan (1 bed / 1 bath)",
          source: "CoStar record, floor plan",
        },
      ],
      tip: "Run the sink and shower: check the water pressure and how fast it drains.",
    }),
    stop({
      kind: "room",
      key: "room-5",
      title: "Bedroom",
      room_label: "Bedroom",
      sweep_id: "fx-sweep-04",
      sweep_count: 1,
      sweep_ids: ["fx-sweep-04"],
      position: [3, 1.4, 5],
      rotation_quat: Q,
      facts: [
        {
          text: "1 bedroom in this floor plan (1 bed / 1 bath)",
          source: "CoStar record, floor plan",
        },
      ],
      tip: "Check the windows, the closet and the outlets, and your phone signal.",
    }),
    stop({
      kind: "outro",
      key: "outro",
      title: "Now see it in person",
      tip: "Book nothing and pay nothing until you have seen it. Take this list with you.",
    }),
  ],
  links: {
    tour_prep: "/prep/place/fixture-bldg-1",
    tour_prep_api: "/places/fixture-bldg-1/tour-prep",
    tour_draft_hint: "Draft a tour request from the results page of your case.",
  },
};
