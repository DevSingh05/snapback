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
export const HOUSTON: [number, number] = [-95.393, 29.748];

const TOKENS = [
  "land",
  "water",
  "park",
  "road",
  "road-case",
  "bldg",
  "bldg-flat",
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
  near: "col-near",
} as const;

type Layer = Record<string, unknown>;
const FAR_SWITCH = 13.4; // below: wide, tall columns that read as a skyline; above: slim ones

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
    "columns-far": { type: "geojson", data: columns(data.places, 95, 5.2, data.passed) },
    "columns-near": { type: "geojson", data: columns(data.places, 15, 1.5, data.passed) },
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
            "fill-extrusion-height": ["+", ["get", "h"], 6],
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
      ...column(L.near, "columns-near", { minzoom: FAR_SWITCH }),
    );
  }
  out.push(
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
    ...road("road-minor", ["minor", "service", "tertiary"], 0.6, 12),
    ...road("road-major", ["primary", "secondary", "trunk"], 0.95, 9),
    ...road("road-motorway", ["motorway"], 1.35, 7),
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
          minzoom: 12.5,
          paint: {
            "fill-extrusion-color": p.bldg,
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": 0.82,
            "fill-extrusion-vertical-gradient": true,
          },
        },
    // A thin, paler slab on each roof: it gives every building a lit top edge.
    ...(look === "paper"
      ? []
      : [
          {
            id: "bldg-roof",
            type: "fill-extrusion",
            ...src,
            "source-layer": "building",
            minzoom: 14,
            paint: {
              "fill-extrusion-color": p.halo,
              "fill-extrusion-base": ["coalesce", ["get", "render_height"], 6],
              "fill-extrusion-height": ["+", ["coalesce", ["get", "render_height"], 6], 0.8],
              "fill-extrusion-opacity": 0.7,
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
    light: { anchor: "map", position: [1.4, 315, 42], intensity: 0.55, color: p.halo },
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
    ? { center: HOUSTON, zoom: narrow ? 10.9 : 11.9, pitch: 58, bearing: -18 }
    : { center: HOUSTON, zoom: narrow ? 10.6 : 11.6, pitch: 0, bearing: 0 };
}
