import type { TourStop } from "../../contracts";
import { PAN_DEG } from "./timeline";
import { stopMove } from "../../tour/walkMove";
import type { ShowcaseSdk } from "../../twin/showcase";

// The real view's camera: the only place the player talks to the Matterport Showcase SDK. The
// transport's cues come in; Sweep.moveTo and Camera.rotate go out. In explore mode the transport
// sends no cues, so nothing here runs and Showcase's own tap-to-move and drag-to-look are in charge.

/** The slice of the Showcase SDK the player uses, on top of the app's own slice. Every extra
 *  part is optional, so an SDK (or a test fake) without it still walks the stops. */
export type PlayerSdk = ShowcaseSdk & {
  Camera?: {
    rotate(horizontal: number, vertical: number, options?: { speed?: number }): Promise<unknown>;
  };
  Sweep: ShowcaseSdk["Sweep"] & {
    current?: {
      subscribe(on: (sweep: { sid?: string; id?: string }) => void): { cancel(): void };
    };
  };
};

export interface CameraDriver {
  /** Put the camera at a stop, turned `panDeg` into its pan. */
  goto(
    stop: TourStop,
    at: { panDeg: number; instant: boolean; speed: number; next?: TourStop },
  ): void;
  /** Turn the camera by `deg` over `ms`. */
  pan(deg: number, ms: number): void;
  /** The stop nearest to where the person has walked to, or null when it cannot be told. */
  nearestStop(stops: TourStop[]): number | null;
  dispose(): void;
}

interface Options {
  /** The sweep ids of the loaded model. A stop outside them is never swapped for another. */
  sweeps: string[];
  onStatus?: (text: string) => void;
}

const FLY_MS = 2000;

const wrap = (deg: number) => ((((deg + 180) % 360) + 360) % 360) - 180;
type Places = Record<string, { x: number; z: number }>;

/** The yaw that faces from one sweep to another, in the Showcase's frame: 0 looks down -Z, and a
 *  turn to the left is positive (a clockwise Camera.rotate lowers it). */
function headingTo(places: Places, from: string, to: string | null | undefined): number | null {
  const a = places[from];
  const b = to ? places[to] : undefined;
  if (!a || !b || (a.x === b.x && a.z === b.z)) return null;
  return (Math.atan2(-(b.x - a.x), -(b.z - a.z)) * 180) / Math.PI;
}

export function createSdkDriver(sdk: PlayerSdk, { sweeps, onStatus }: Options): CameraDriver {
  let move = 0;
  let moving = false;
  let here: string | null = null;
  // Where the model's sweeps are, in the Showcase's frame, so a pan can face the next stop.
  const places: Places = {};
  const data = sdk.Sweep.data.subscribe({
    onCollectionUpdated(all) {
      for (const [sid, v] of Object.entries(all)) {
        const p = (v as { position?: { x?: number; z?: number } }).position;
        if (p && typeof p.x === "number" && typeof p.z === "number") places[sid] = { x: p.x, z: p.z };
      }
    },
  });
  // How much of the plain pan each chunk keeps, and which way it turns: set at every stop.
  let panScale = 1;
  const watch = sdk.Sweep.current?.subscribe((sweep) => {
    here = sweep.sid || sweep.id || here;
  });

  return {
    goto(stop, { panDeg, instant, speed, next }) {
      const to = stopMove(stop, instant);
      if (!to) return;
      if (!sweeps.includes(to.sweepId)) {
        onStatus?.("This stop is not in the loaded 3D model");
        return;
      }
      const mine = ++move;
      moving = true;
      // Matterport's rule for a guided tour: always turn toward the next highlight. A stop with an
      // ad photo keeps the photo's own view on arrival, then turns toward the next stop (never
      // more than one pan's worth); any other stop opens already facing that way.
      const bearing = headingTo(
        places,
        to.sweepId,
        next?.photos.find((p) => p.sweep_id && p.rotation_quat)?.sweep_id ?? next?.sweep_id,
      );
      const hasPhoto = stop.photos.some((p) => p.sweep_id && p.rotation_quat);
      let startYaw = to.options.rotation.y;
      panScale = 1;
      if (bearing !== null) {
        if (hasPhoto) {
          const turn = Math.max(-PAN_DEG, Math.min(-wrap(bearing - startYaw), PAN_DEG));
          panScale = turn / PAN_DEG;
        } else {
          startYaw = bearing + PAN_DEG / 2;
        }
      }
      const options = {
        ...to.options,
        transitionTime: instant ? 0 : Math.round(FLY_MS / speed),
        rotation: { x: to.options.rotation.x, y: startYaw - panScale * panDeg },
      };
      sdk.Sweep.moveTo(to.sweepId, options)
        .then(() => mine === move && onStatus?.(`At: ${stop.title}`))
        .catch(
          (e: unknown) =>
            mine === move &&
            onStatus?.(e instanceof Error ? e.message : "Could not move the 3D view"),
        )
        .finally(() => {
          if (mine === move) moving = false;
        });
    },

    pan(deg, ms) {
      // A turn sent mid-flight would cut the move short: the pan waits for the camera to land.
      if (moving || !sdk.Camera || ms <= 0) return;
      const turn = deg * panScale;
      if (Math.abs(turn) < 0.5) return;
      sdk.Camera.rotate(turn, 0, { speed: Math.abs(turn) / (ms / 1000) }).catch(() => {
        // The person took the camera, or a move replaced the turn. Nothing to do.
      });
    },

    nearestStop(stops) {
      if (!here) return null;
      const at = stops.findIndex(
        (s) =>
          s.sweep_id === here ||
          s.sweep_ids.includes(here!) ||
          s.photos.some((p) => p.sweep_id === here),
      );
      return at >= 0 ? at : null;
    },

    dispose() {
      move += 1;
      watch?.cancel();
      data?.cancel();
    },
  };
}
