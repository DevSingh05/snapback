// The one place MapLibre GL is loaded, and the narrow slice of its API the map screen uses.
// It is imported with import() from the /map route only, so the home bundle does not grow.
//
// NOT INSTALLED YET. `maplibre-gl` is approved (decisions R-M3) but the npm install has not been
// run on this branch, so loadMapLibre() rejects and the map screen shows its "could not start"
// state with the full list of places. To turn the map on:
//   1. npm install maplibre-gl@6.16.0 -w apps/web --save-exact   (BSD-3-Clause, released Oct 25 2026)
//   2. replace the body of loadMapLibre() with the two lines in its comment.
// Nothing else in the app changes; CityMap is written against the MapApi slice below.

export const MAPLIBRE_VERSION = "6.16.0";

export interface Point {
  x: number;
  y: number;
}
export interface LngLat {
  lng: number;
  lat: number;
}
export interface RenderedFeature {
  geometry: { type: string; coordinates: unknown };
  properties: Record<string, unknown>;
  layer: { id: string };
}
export interface MapClick {
  point: Point;
  lngLat: LngLat;
}
export interface CameraMove {
  center?: [number, number];
  zoom?: number;
  pitch?: number;
  bearing?: number;
  duration?: number;
  padding?: { top: number; right: number; bottom: number; left: number };
  essential?: boolean;
}
export interface GeoJsonSource {
  setData(data: unknown): void;
  getClusterExpansionZoom(clusterId: number): Promise<number>;
}
export interface MapApi {
  on(event: "load" | "idle" | "moveend" | "error", fn: (e?: unknown) => void): void;
  on(event: "click", fn: (e: MapClick) => void): void;
  on(event: "mousemove", fn: (e: MapClick) => void): void;
  once(event: "idle" | "moveend" | "load" | "styledata", fn: () => void): void;
  remove(): void;
  resize(): void;
  setStyle(style: unknown): void;
  getLayer(id: string): unknown;
  getSource(id: string): GeoJsonSource | undefined;
  queryRenderedFeatures(
    point: Point | [Point, Point],
    opts?: { layers?: string[] },
  ): RenderedFeature[];
  project(lngLat: [number, number]): Point;
  flyTo(move: CameraMove): void;
  easeTo(move: CameraMove): void;
  jumpTo(move: CameraMove): void;
  getZoom(): number;
  getBearing(): number;
  getCanvas(): HTMLCanvasElement;
  isStyleLoaded(): boolean | void;
}
export interface MapOptions extends CameraMove {
  container: HTMLElement;
  style: unknown;
  attributionControl: false;
  maxPitch?: number;
  minZoom?: number;
  maxZoom?: number;
  cooperativeGestures?: boolean;
}
export interface MapLibre {
  Map: new (options: MapOptions) => MapApi;
}

export function loadMapLibre(): Promise<MapLibre> {
  // After the install:
  //   await import("maplibre-gl/dist/maplibre-gl.css");
  //   return (await import("maplibre-gl")) as unknown as MapLibre;
  return Promise.reject(
    new Error(`maplibre-gl ${MAPLIBRE_VERSION} is not installed in this build.`),
  );
}
