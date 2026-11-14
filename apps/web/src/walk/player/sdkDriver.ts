import type { TourStop } from "../../contracts";
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
  goto(stop: TourStop, at: { panDeg: number; instant: boolean; speed: number }): void;
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

export function createSdkDriver(sdk: PlayerSdk, { sweeps, onStatus }: Options): CameraDriver {
  let move = 0;
  let moving = false;
  let here: string | null = null;
  const watch = sdk.Sweep.current?.subscribe((sweep) => {
    here = sweep.sid || sweep.id || here;
  });

  return {
    goto(stop, { panDeg, instant, speed }) {
      const to = stopMove(stop, instant);
      if (!to) return;
      if (!sweeps.includes(to.sweepId)) {
        onStatus?.("This stop is not in the loaded 3D model");
        return;
      }
      const mine = ++move;
      moving = true;
      const options = {
        ...to.options,
        transitionTime: instant ? 0 : Math.round(FLY_MS / speed),
        rotation: { x: to.options.rotation.x, y: to.options.rotation.y + panDeg },
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
      sdk.Camera.rotate(deg, 0, { speed: Math.abs(deg) / (ms / 1000) }).catch(() => {
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
    },
  };
}
