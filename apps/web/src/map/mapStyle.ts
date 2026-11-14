import { columns } from "./geometry";
import type { PlaceFeature } from "./types";

// The map's look, built from our tokens. Colours are read from tokens.css at run time
// (--map-*), so the map follows the light and dark sets and no colour is written here.
// Tiles: OpenFreeMap vector tiles in the OpenMapTiles schema; if they do not answer, a plain
// OpenStreetMap raster style takes over (flat, no 3D buildings). Both carry attribution.

export type Look = "glass" | "paper";

export const TILEJSON = "https://tiles.openfreemap.org/planet";
const GLYPHS = "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf";
const OSM_RASTER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const HOUSTON: [number, number] = [-95.3895, 29.7455]; // frames Midtown and Downtown beside the left panels
const MIDTOWN: [number, number] = [-95.376, 29.747];

const TOKENS = [
  "land",
  "water",
  "park",
  "road",
  "road-case",
  "bldg",
  "bldg-flat",
  "roof",
  "win",
  "chip",
  "on-chip",
  "road-glow",
  "label",
  "halo",
  "sky",
  "horizon",
  "col",
  "col-off",
  "col-cap",
  "glow",
  "pick",
  "cluster",
  "on-cluster",
] as const;
export type Palette = Record<(typeof TOKENS)[number], string>;

export function readPalette(el: Element = document.documentElement): Palette {
  const css = getComputedStyle(el);
  const out = {} as Palette;
  for (const t of TOKENS) out[t] = css.getPropertyValue(`--map-${t}`).trim() || "transparent";
  return out;
}

export interface PlaceData {
  places: PlaceFeature[];
  passed: ReadonlySet<string>;
}

// Layer ids the map wrapper asks about.
export const L = {
  building: "bldg-3d",
  buildingFlat: "bldg-flat",
  cluster: "cluster",
  point: "place-point",
  far: "col-far",
  mid: "col-mid",
  near: "col-near",
} as const;

type Layer = Record<string, unknown>;
const FAR_SWITCH = 12.2; // below: wide, tall columns that read as a skyline
const NEAR_SWITCH = 14.6; // above: slim beacons beside the real buildings

export function placeSources(data: PlaceData): Record<string, unknown> {
  return {
    places: {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: data.places.map((f) => ({
          ...f,
          properties: { ...f.properties, passed: data.passed.has(f.properties.pid) },
        })),
      },
      cluster: true,
      clusterMaxZoom: 10,
      clusterRadius: 48,
    },
    "columns-far": { type: "geojson", data: columns(data.places, 90, 3.4, data.passed) },
    "columns-mid": { type: "geojson", data: columns(data.places, 32, 1.9, data.passed) },
    "columns-near": { type: "geojson", data: columns(data.places, 6, 0.3, data.passed) },
    picked: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
    "picked-point": { type: "geojson", data: { type: "FeatureCollection", features: [] } },
  };
}

function placeLayers(p: Palette, look: Look, vector: boolean): Layer[] {
  const colour = ["case", ["get", "fits"], p.col, p["col-off"]];
  const pointColour = ["case", ["get", "fits_brief"], p.col, p["col-off"]];
  const flat = look === "paper" || !vector;
  const out: Layer[] = [
    // A pool of light on the ground under each place that fits.
    {
      id: "place-glow",
      type: "circle",
      source: "places",
      filter: ["all", ["!", ["has", "point_count"]], ["get", "fits_brief"]],
      paint: {
        "circle-color": p.glow,
        "circle-blur": 1,
        "circle-opacity": flat ? 0.3 : 0.55,
        "circle-pitch-alignment": "map",
        "circle-radius": ["interpolate", ["exponential", 1.8], ["zoom"], 10, 10, 13, 34, 17, 120],
      },
    },
    // A crisp ring on the ground at every place, so each one reads as a marked spot.
    {
      id: "place-ring",
      type: "circle",
      source: "places",
      filter: ["!", ["has", "point_count"]],
      paint: {
        "circle-color": p.glow,
        "circle-opacity": ["case", ["get", "fits_brief"], 0.14, 0],
        "circle-stroke-color": pointColour,
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 15, 2],
        "circle-stroke-opacity": ["case", ["get", "passed"], 0.3, 0.9],
        "circle-pitch-alignment": "map",
        "circle-radius": ["interpolate", ["exponential", 1.8], ["zoom"], 10, 4, 13, 13, 17, 62],
      },
    },
    {
      id: "picked-ring",
      type: "circle",
      source: "picked-point",
      paint: {
        "circle-color": p.glow,
        "circle-opacity": 0.18,
        "circle-stroke-color": p.pick,
        "circle-stroke-width": 2,
        "circle-pitch-alignment": "map",
        "circle-radius": ["interpolate", ["exponential", 1.8], ["zoom"], 11, 16, 14, 46, 17, 150],
      },
    },
    {
      id: "picked-bldg",
      type: flat ? "fill" : "fill-extrusion",
      source: "picked",
      paint: flat
        ? { "fill-color": p.pick, "fill-opacity": 0.85 }
        : {
            "fill-extrusion-color": p.pick,
            "fill-extrusion-height": tall(["get", "h"], 3),
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.96,
          },
    },
  ];
  if (flat) {
    out.push(
      {
        id: "place-shadow",
        type: "circle",
        source: "places",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": p.label,
          "circle-blur": 0.9,
          "circle-opacity": 0.28,
          "circle-translate": [0, 5],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 7, 16, 16],
        },
      },
      {
        id: L.point,
        type: "circle",
        source: "places",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": pointColour,
          "circle-opacity": ["case", ["get", "passed"], 0.35, 1],
          "circle-stroke-color": p.halo,
          "circle-stroke-width": 2,
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            10,
            ["+", 4, ["min", ["get", "n_plans"], 5]],
            16,
            ["+", 9, ["*", 1.6, ["min", ["get", "n_plans"], 5]]],
          ],
        },
      },
      {
        id: "place-scan",
        type: "circle",
        source: "places",
        filter: ["all", ["!", ["has", "point_count"]], ["get", "has_scan"]],
        paint: {
          "circle-color": p["col-cap"],
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 16, 4.5],
        },
      },
    );
  } else {
    const column = (id: string, source: string, zoom: Layer): Layer[] => [
      {
        id,
        type: "fill-extrusion",
        source,
        ...zoom,
        paint: {
          "fill-extrusion-color": colour,
          "fill-extrusion-height": ["get", "h"],
          "fill-extrusion-opacity": 0.9,
          "fill-extrusion-vertical-gradient": true,
        },
        filter: ["!", ["get", "passed"]],
      },
      {
        id: `${id}-passed`,
        type: "fill-extrusion",
        source,
        ...zoom,
        filter: ["get", "passed"],
        paint: {
          "fill-extrusion-color": p["col-off"],
          "fill-extrusion-height": ["*", 0.25, ["get", "h"]],
          "fill-extrusion-opacity": 0.5,
        },
      },
      // A white lantern on top of every column whose place has a 3D scan on record.
      {
        id: `${id}-cap`,
        type: "fill-extrusion",
        source,
        ...zoom,
        filter: ["all", ["get", "scan"], ["!", ["get", "passed"]]],
        paint: {
          "fill-extrusion-color": p["col-cap"],
          "fill-extrusion-base": ["get", "h"],
          "fill-extrusion-height": ["get", "cap"],
          "fill-extrusion-vertical-gradient": false,
        },
      },
    ];
    out.push(
      // An unseen hit target at each place's foot, so a tap near a slim column still lands.
      {
        id: L.point,
        type: "circle",
        source: "places",
        filter: ["!", ["has", "point_count"]],
        paint: { "circle-opacity": 0, "circle-radius": 14, "circle-pitch-alignment": "map" },
      },
      ...column(L.far, "columns-far", { minzoom: 10, maxzoom: FAR_SWITCH }),
      ...column(L.mid, "columns-mid", { minzoom: FAR_SWITCH, maxzoom: NEAR_SWITCH }),
      ...column(L.near, "columns-near", { minzoom: NEAR_SWITCH }),
    );
  }
  out.push(
    // At close zoom each place carries its lowest asking rent on a chip; the map key says what
    // the figure is and that it is as of CoStar's last research.
    {
      id: "place-rent",
      type: "symbol",
      source: "places",
      minzoom: 13.6,
      filter: ["all", ["!", ["has", "point_count"]], ["!", ["get", "passed"]]],
      layout: {
        "text-field": [
          "case",
          ["==", ["get", "rent_from"], null],
          "on record",
          [
            "concat",
            "from $",
            ["number-format", ["get", "rent_from"], { "max-fraction-digits": 0 }],
          ],
        ],
        "text-font": ["Noto Sans Bold"],
        "text-size": 12,
        "text-anchor": "top",
        "text-offset": [0, 1.2],
        "icon-image": IMG.chip,
        "icon-text-fit": "both",
        "icon-text-fit-padding": [4, 8, 4, 8],
        "symbol-sort-key": ["case", ["get", "fits_brief"], 0, 1],
      },
      paint: { "text-color": p["on-chip"] },
    },
    {
      id: L.cluster,
      type: "circle",
      source: "places",
      filter: ["has", "point_count"],
      paint: {
        "circle-color": p.cluster,
        "circle-stroke-color": p.glow,
        "circle-stroke-width": 3,
        "circle-stroke-opacity": 0.45,
        "circle-radius": ["step", ["get", "point_count"], 18, 10, 23, 50, 29, 200, 36],
      },
    },
    {
      id: "cluster-count",
      type: "symbol",
      source: "places",
      filter: ["has", "point_count"],
      layout: {
        "text-field": ["get", "point_count_abbreviated"],
        "text-font": ["Noto Sans Bold"],
        "text-size": 14,
        "text-allow-overlap": true,
      },
      paint: { "text-color": p["on-cluster"] },
    },
  );
  return out;
}

// Building heights come from the tiles (render_height, with 7 m where the map has none). They
// are drawn taller than life at city zoom so the whole city reads as 3D, easing to true height
// close in. `plus` lifts a layer above the roof line.
const BLDG_H = ["max", ["coalesce", ["get", "render_height"], 7], 7];
const BLDG_BASE = ["coalesce", ["get", "render_min_height"], 0];
const tall = (h: unknown, plus = 0) => [
  "interpolate",
  ["linear"],
  ["zoom"],
  12,
  ["+", ["*", 3, h], plus * 3],
  14,
  ["+", ["*", 1.9, h], plus * 2],
  16,
  ["+", ["*", 1.15, h], plus],
];
// Images the style names; CityMap draws them from the palette when MapLibre asks for them.
export const IMG = { facade: "sb-facade", chip: "sb-chip" } as const;

const ROAD_WIDTH = (k: number) => [
  "interpolate",
  ["exponential", 1.6],
  ["zoom"],
  9,
  0.4 * k,
  13,
  1.6 * k,
  17,
  11 * k,
];

function baseLayers(p: Palette, look: Look): Layer[] {
  const src = { source: "openmaptiles" };
  const road = (id: string, classes: string[], k: number, minzoom: number): Layer[] => [
    {
      id: `${id}-case`,
      type: "line",
      ...src,
      "source-layer": "transportation",
      minzoom,
      filter: ["in", ["get", "class"], ["literal", classes]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": p["road-case"], "line-width": ROAD_WIDTH(k), "line-gap-width": 0 },
    },
    {
      id,
      type: "line",
      ...src,
      "source-layer": "transportation",
      minzoom,
      filter: ["in", ["get", "class"], ["literal", classes]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": p.road, "line-width": ROAD_WIDTH(k * 0.72) },
    },
  ];
  const label = (
    id: string,
    layer: string,
    filter: unknown,
    size: number,
    extra: Layer = {},
  ): Layer => ({
    id,
    type: "symbol",
    ...src,
    "source-layer": layer,
    filter,
    ...extra,
    layout: {
      "text-field": ["coalesce", ["get", "name:en"], ["get", "name"]],
      "text-font": ["Noto Sans Regular"],
      "text-size": size,
      "text-letter-spacing": 0.08,
      "text-transform": "uppercase",
      "text-max-width": 7,
      ...((extra.layout as Layer | undefined) ?? {}),
    },
    paint: {
      "text-color": p.label,
      "text-halo-color": p.halo,
      "text-halo-width": 1.4,
      "text-opacity": 0.85,
    },
  });
  return [
    { id: "land", type: "background", paint: { "background-color": p.land } },
    {
      id: "park",
      type: "fill",
      ...src,
      "source-layer": "park",
      paint: { "fill-color": p.park, "fill-opacity": 0.7 },
    },
    {
      id: "green",
      type: "fill",
      ...src,
      "source-layer": "landcover",
      filter: ["in", ["get", "class"], ["literal", ["wood", "grass"]]],
      paint: { "fill-color": p.park, "fill-opacity": 0.5 },
    },
    {
      id: "water",
      type: "fill",
      ...src,
      "source-layer": "water",
      paint: { "fill-color": p.water },
    },
    {
      id: "waterway",
      type: "line",
      ...src,
      "source-layer": "waterway",
      paint: {
        "line-color": p.water,
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1, 16, 5],
      },
    },
    {
      id: "road-glow",
      type: "line",
      ...src,
      "source-layer": "transportation",
      minzoom: 9,
      filter: ["in", ["get", "class"], ["literal", ["motorway", "trunk", "primary"]]],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": p["road-glow"],
        "line-width": ROAD_WIDTH(3.4),
        "line-blur": 8,
        "line-opacity": 0.55,
      },
    },
    ...road("road-minor", ["minor", "service", "tertiary"], 0.55, 12),
    ...road("road-major", ["primary", "secondary", "trunk"], 1.05, 9),
    ...road("road-motorway", ["motorway"], 1.7, 7),
    look === "paper"
      ? {
          id: L.buildingFlat,
          type: "fill",
          ...src,
          "source-layer": "building",
          minzoom: 13,
          paint: { "fill-color": p["bldg-flat"], "fill-opacity": 0.9 },
        }
      : {
          id: L.building,
          type: "fill-extrusion",
          ...src,
          "source-layer": "building",
          minzoom: 12,
          paint: {
            "fill-extrusion-color": p.bldg,
            "fill-extrusion-height": tall(BLDG_H),
            "fill-extrusion-base": tall(BLDG_BASE),
            "fill-extrusion-opacity": 0.9,
            "fill-extrusion-vertical-gradient": true,
          },
        },
    ...(look === "paper"
      ? []
      : [
          // Close in, the walls carry floor bands and windows (a small pattern drawn from the
          // tokens), laid over the plain walls.
          {
            id: "bldg-facade",
            type: "fill-extrusion",
            ...src,
            "source-layer": "building",
            minzoom: 14.4,
            paint: {
              "fill-extrusion-pattern": IMG.facade,
              "fill-extrusion-height": tall(BLDG_H),
              "fill-extrusion-base": tall(BLDG_BASE),
              "fill-extrusion-opacity": 0.9,
            },
          },
          // A thin, paler slab on each roof: it gives every building a lit top edge.
          {
            id: "bldg-roof",
            type: "fill-extrusion",
            ...src,
            "source-layer": "building",
            minzoom: 13,
            paint: {
              "fill-extrusion-color": p.roof,
              "fill-extrusion-base": tall(BLDG_H),
              "fill-extrusion-height": tall(BLDG_H, 0.9),
              "fill-extrusion-opacity": 0.9,
              "fill-extrusion-vertical-gradient": false,
            },
          },
        ]),
    label(
      "road-name",
      "transportation_name",
      ["in", ["get", "class"], ["literal", ["primary", "secondary", "trunk"]]],
      10,
      {
        minzoom: 14,
        layout: {
          "symbol-placement": "line",
          "text-transform": "none",
          "text-letter-spacing": 0.02,
        },
      },
    ),
    label(
      "area-name",
      "place",
      ["in", ["get", "class"], ["literal", ["suburb", "neighbourhood", "quarter"]]],
      11,
      {
        minzoom: 11,
      },
    ),
    label("city-name", "place", ["==", ["get", "class"], "city"], 15, { maxzoom: 12 }),
  ];
}

export function buildStyle(p: Palette, look: Look, data: PlaceData): Record<string, unknown> {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      openmaptiles: { type: "vector", url: TILEJSON },
      ...placeSources(data),
    },
    // One light, from the north-west and fixed to the map, shades every wall the same way.
    light: { anchor: "map", position: [1.3, 300, 38], intensity: 0.32, color: p["col-cap"] },
    sky:
      look === "glass"
        ? {
            "sky-color": p.sky,
            "horizon-color": p.horizon,
            "fog-color": p.horizon,
            "sky-horizon-blend": 0.6,
            "horizon-fog-blend": 0.7,
            "fog-ground-blend": 0.55,
          }
        : undefined,
    layers: [...baseLayers(p, look), ...placeLayers(p, look, true)],
  };
}

// The fallback when the vector tiles do not answer: OpenStreetMap's own raster tiles, light use
// only, flat, with pins in place of columns.
export function rasterStyle(p: Palette, data: PlaceData): Record<string, unknown> {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      osm: {
        type: "raster",
        tiles: [OSM_RASTER],
        tileSize: 256,
        maxzoom: 19,
        attribution: "© OpenStreetMap contributors",
      },
      ...placeSources(data),
    },
    layers: [
      { id: "land", type: "background", paint: { "background-color": p.land } },
      {
        id: "osm",
        type: "raster",
        source: "osm",
        paint: { "raster-saturation": -0.55, "raster-opacity": 0.9 },
      },
      ...placeLayers(p, "paper", false),
    ],
  };
}

export function camera(look: Look, narrow: boolean) {
  return look === "glass"
    ? { center: narrow ? MIDTOWN : HOUSTON, zoom: narrow ? 13.02 : 13.1, pitch: 57, bearing: -20 }
    : { center: HOUSTON, zoom: narrow ? 10.6 : 11.6, pitch: 0, bearing: 0 };
}

type Rgba = [number, number, number, number];

// Any CSS colour to RGBA bytes, by letting a canvas paint it. Null where there is no canvas.
function rgba(colour: string): Rgba | null {
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = colour;
  ctx.fillRect(0, 0, 1, 1);
  const d = ctx.getImageData(0, 0, 1, 1).data;
  return [d[0]!, d[1]!, d[2]!, d[3]!];
}

export interface StyleImage {
  image: { width: number; height: number; data: Uint8ClampedArray };
  options?: {
    pixelRatio?: number;
    stretchX?: [number, number][];
    stretchY?: [number, number][];
    content?: [number, number, number, number];
  };
}

// The two small images the style names, painted from the palette: the wall pattern (one floor
// band with two windows, repeated up and along every wall) and the rent chip's plate.
export function styleImage(id: string, p: Palette): StyleImage | null {
  if (id === IMG.facade) {
    const wall = rgba(p.bldg);
    const win = rgba(p.win);
    const band = rgba(p["road-case"]);
    if (!wall || !win || !band) return null;
    const size = 32;
    const data = new Uint8ClampedArray(size * size * 4);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const row = y % 16;
        const col = x % 16;
        const px = row === 15 ? band : row >= 4 && row <= 10 && col >= 4 && col <= 11 ? win : wall;
        data.set(px, (y * size + x) * 4);
      }
    }
    return { image: { width: size, height: size, data } };
  }
  if (id === IMG.chip) {
    const plate = rgba(p.chip);
    const edge = rgba(p["col-off"]);
    if (!plate || !edge) return null;
    const size = 12;
    const data = new Uint8ClampedArray(size * size * 4);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const rim = x === 0 || y === 0 || x === size - 1 || y === size - 1;
        data.set(rim ? edge : plate, (y * size + x) * 4);
      }
    }
    return {
      image: { width: size, height: size, data },
      options: { stretchX: [[3, 9]], stretchY: [[3, 9]], content: [3, 3, 9, 9], pixelRatio: 1 },
    };
  }
  return null;
}
