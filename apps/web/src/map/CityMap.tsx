import { useEffect, useRef } from "react";

import { nearestPlace, pickPolygon } from "./geometry";
import { loadMapLibre } from "./maplibre";
import type { MapApi, MapClick, RenderedFeature } from "./maplibre";
import {
  IMG,
  L,
  TILEJSON,
  buildStyle,
  camera,
  placeSources,
  rasterStyle,
  readPalette,
  styleImage,
} from "./mapStyle";
import type { Look } from "./mapStyle";
import { S } from "./strings";
import type { PlaceFeature } from "./types";

export type MapStatus = "loading" | "ready" | "raster" | "failed";

interface Props {
  places: PlaceFeature[];
  passed: ReadonlySet<string>;
  selectedPid: string | null;
  look: Look;
  forceRaster?: boolean;
  reducedMotion: boolean;
  // Screen space covered by panels, so a picked place lands in the part of the map still in view.
  padding: { top: number; right: number; bottom: number; left: number };
  onPick: (pid: string) => void;
  onMiss: () => void;
  onStatus: (status: MapStatus) => void;
}

const EMPTY = { type: "FeatureCollection", features: [] };

async function vectorTilesAnswer(): Promise<boolean> {
  try {
    const res = await fetch(TILEJSON, { signal: AbortSignal.timeout(8000) });
    return res.ok;
  } catch {
    return false;
  }
}

// Our own thin wrapper around MapLibre GL: no react-map-gl. React owns the data and the picked
// place; this component owns the camera and the layers.
export function CityMap(props: Props) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapApi | null>(null);
  const live = useRef(props);
  live.current = props;
  const vector = useRef(true);
  const ready = useRef<() => void>(() => {});

  const api = useRef<{
    flyToPlace: (f: PlaceFeature) => boolean;
    showPicked: () => void;
    setData: () => void;
    restyle: () => void;
  } | null>(null);

  useEffect(() => {
    let dead = false;
    let map: MapApi | null = null;
    const cleanups: (() => void)[] = [];
    let orbiting = false;
    const orbit = () => {
      if (!map || !orbiting || live.current.selectedPid) return;
      map.easeTo({ bearing: map.getBearing() + 9, duration: 20000, easing: (t) => t });
    };

    const style = () => {
      const p = live.current;
      const data = { places: p.places, passed: p.passed };
      return vector.current
        ? buildStyle(readPalette(), p.look, data)
        : rasterStyle(readPalette(), data);
    };

    const hitLayers = () =>
      [L.cluster, L.point, L.far, L.mid, L.near].filter((id) => map?.getLayer(id) != null);

    const onClick = (e: MapClick) => {
      if (!map) return;
      const hits = map.queryRenderedFeatures(e.point, { layers: hitLayers() });
      const cluster = hits.find((f) => f.layer.id === L.cluster);
      if (cluster) {
        const at = (cluster.geometry.coordinates as [number, number]).slice(0, 2) as [
          number,
          number,
        ];
        void map
          .getSource("places")
          ?.getClusterExpansionZoom(Number(cluster.properties.cluster_id))
          .then((zoom) => move({ center: at, zoom: zoom + 0.4 }));
        return;
      }
      const place = hits.find((f) => typeof f.properties.pid === "string");
      if (place) {
        live.current.onPick(String(place.properties.pid));
        return;
      }
      // A building: it belongs to the nearest researched place within 40 m, or to none.
      const layer = [L.building, L.buildingFlat].find((id) => map!.getLayer(id) != null);
      if (!layer || map.queryRenderedFeatures(e.point, { layers: [layer] }).length === 0) return;
      const near = nearestPlace(live.current.places, [e.lngLat.lng, e.lngLat.lat], 40);
      if (near) live.current.onPick(near.properties.pid);
      else live.current.onMiss();
    };

    const move = (to: {
      center: [number, number];
      zoom: number;
      pitch?: number;
      bearing?: number;
    }) => {
      if (!map) return;
      orbiting = false;
      const target = { ...to, padding: live.current.padding };
      if (live.current.reducedMotion) map.jumpTo(target);
      else map.flyTo({ ...target, duration: 1200, essential: true });
    };

    // Colour the picked place's own building, taken from the rendered tiles at its point.
    const showPicked = () => {
      if (!map) return;
      const pid = live.current.selectedPid;
      const f = live.current.places.find((x) => x.properties.pid === pid);
      const ring = f ? { type: "FeatureCollection", features: [f] } : EMPTY;
      map.getSource("picked-point")?.setData(ring);
      let found: RenderedFeature | undefined;
      let shape: ReturnType<typeof pickPolygon> = null;
      const layer = [L.building, L.buildingFlat].find((id) => map!.getLayer(id) != null);
      if (f && layer) {
        // Look in a small box around the place's point, and keep the one building it sits in.
        const at = map.project(f.geometry.coordinates);
        const hits = map.queryRenderedFeatures(
          [
            { x: at.x - 24, y: at.y - 24 },
            { x: at.x + 24, y: at.y + 24 },
          ],
          { layers: [layer] },
        );
        for (const hit of hits) {
          shape = pickPolygon(hit.geometry, f.geometry.coordinates);
          if (shape) {
            found = hit;
            break;
          }
        }
      }
      // For tests and screenshots: whether the picked place has a building of its own lit.
      if (box.current)
        box.current.dataset.picked = f ? (found && shape ? "building" : "point") : "none";
      map.getSource("picked")?.setData(
        found && shape
          ? {
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  geometry: shape,
                  properties: { h: Math.max(7, Number(found.properties.render_height ?? 7)) },
                },
              ],
            }
          : EMPTY,
      );
    };

    api.current = {
      flyToPlace: (f) => {
        if (!map) return false;
        const flat = !vector.current || live.current.look === "paper";
        move({
          center: f.geometry.coordinates,
          zoom: 16.2,
          pitch: flat ? 0 : 62,
          bearing: flat ? 0 : map.getBearing() + 38,
        });
        map.getSource("picked")?.setData(EMPTY);
        map.once("moveend", () => map?.once("idle", showPicked));
        return true;
      },
      showPicked,
      setData: () => {
        if (!map) return;
        const p = live.current;
        const sources = placeSources({ places: p.places, passed: p.passed }) as Record<
          string,
          { data: unknown }
        >;
        for (const id of ["places", "columns-far", "columns-mid", "columns-near"]) {
          map.getSource(id)?.setData(sources[id]!.data);
        }
      },
      restyle: () => {
        // The two painted images follow the palette, so they are dropped and painted again.
        for (const id of Object.values(IMG)) if (map?.hasImage(id)) map.removeImage(id);
        map?.setStyle(style());
        map?.once("idle", showPicked);
      },
    };

    void (async () => {
      try {
        const [ml, ok] = await Promise.all([
          loadMapLibre(),
          live.current.forceRaster ? Promise.resolve(false) : vectorTilesAnswer(),
        ]);
        if (dead || !box.current) return;
        vector.current = ok;
        const narrow = box.current.clientWidth < 640;
        map = new ml.Map({
          container: box.current,
          style: style(),
          attributionControl: false, // the page prints the attribution line itself, always in view
          maxPitch: 70,
          minZoom: 8.5,
          maxZoom: 18,
          cooperativeGestures: narrow,
          ...camera(ok ? live.current.look : "paper", narrow),
        });
        mapRef.current = map;
        map.on("load", () => {
          if (dead) return;
          live.current.onStatus(ok ? "ready" : "raster");
          ready.current();
          orbiting = ok && live.current.look === "glass" && !live.current.reducedMotion;
          if (orbiting && !live.current.selectedPid) orbit();
        });
        // The style names two small images; paint them from the tokens as soon as a style is in,
        // and again whenever MapLibre says one is missing.
        const paintImages = () => {
          if (!map) return;
          for (const id of Object.values(IMG)) {
            const made = map.hasImage(id) ? null : styleImage(id, readPalette());
            if (made) map.addImage(id, made.image, made.options);
          }
        };
        map.on("styledata", paintImages);
        map.on("styleimagemissing", paintImages);
        map.on("click", onClick);
        // A slow turn of the city while nobody is touching it. It ends at the first touch, key
        // or pick, and never starts under reduced motion.
        const stopOrbit = () => {
          if (!orbiting) return;
          orbiting = false;
          map?.stop();
        };
        const boxEl = box.current;
        for (const ev of ["pointerdown", "wheel", "touchstart", "keydown"] as const) {
          boxEl.addEventListener(ev, stopOrbit, { passive: true });
        }
        cleanups.push(() => {
          for (const ev of ["pointerdown", "wheel", "touchstart", "keydown"] as const) {
            boxEl.removeEventListener(ev, stopOrbit);
          }
        });
        map.on("moveend", () => {
          if (orbiting) orbit();
        });
        map.on("mousemove", (e: MapClick) => {
          const hit = map!.queryRenderedFeatures(e.point, { layers: hitLayers() }).length > 0;
          map!.getCanvas().style.cursor = hit ? "pointer" : "";
        });

        // Follow the theme: rebuild the style from the tokens when the colour scheme flips.
        const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
        const restyle = () => api.current?.restyle();
        mq?.addEventListener("change", restyle);
        const mo = new MutationObserver(restyle);
        mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
        cleanups.push(
          () => mq?.removeEventListener("change", restyle),
          () => mo.disconnect(),
        );
      } catch {
        if (!dead) live.current.onStatus("failed");
      }
    })();

    return () => {
      dead = true;
      cleanups.forEach((fn) => fn());
      map?.remove();
      mapRef.current = null;
      api.current = null;
    };
    // The map is made once; later prop changes go through the effects below.
  }, []);

  // Fly to the picked place once, as soon as the map and the feed both know it. A place named in
  // the address (?place=) is picked before either is ready, so this runs from all three.
  const flown = useRef<string | null>(null);
  const syncPick = () => {
    const p = live.current;
    const f = p.places.find((x) => x.properties.pid === p.selectedPid);
    if (!api.current) return;
    if (!f) {
      flown.current = null;
      api.current.showPicked();
    } else if (flown.current !== f.properties.pid) {
      if (api.current.flyToPlace(f)) flown.current = f.properties.pid;
    }
  };
  ready.current = syncPick;

  useEffect(() => {
    api.current?.setData();
    syncPick();
  }, [props.places, props.passed]);

  useEffect(() => {
    api.current?.restyle();
  }, [props.look]);

  useEffect(() => {
    syncPick();
  }, [props.selectedPid]);

  return <div ref={box} className="city-map" role="region" aria-label={S.mapLabel} />;
}
