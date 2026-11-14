// The one place MapLibre GL is loaded, and the narrow slice of its API the map screen uses.
// It is imported with import() from the /map route only, so the home bundle does not grow.
// MapLibre GL JS 6.16.0 (BSD-3-Clause), pinned exactly in package.json. Version 6 ships its
// worker as a separate file, so the worker's own URL is handed to it here.

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

let loading: Promise<MapLibre> | null = null;

export function loadMapLibre(): Promise<MapLibre> {
  loading ??= (async () => {
    const [ml, worker] = await Promise.all([
      import("maplibre-gl"),
      import("maplibre-gl/dist/maplibre-gl-worker.mjs?url"),
      import("maplibre-gl/dist/maplibre-gl.css"),
    ]);
    ml.setWorkerUrl(worker.default);
    return ml as unknown as MapLibre;
  })();
  return loading;
}
