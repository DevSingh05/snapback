import type { SdkMoveTo } from "./pose";
import { pickSweep } from "./pose";

// Minimal slice of the Matterport Showcase SDK we use.
export interface ShowcaseSdk {
  disconnect(): void;
  Sweep: {
    data: {
      subscribe(o: { onCollectionUpdated(c: Record<string, unknown>): void }): {
        cancel(): void;
      };
    };
    moveTo(id: string, o: SdkMoveTo["options"]): Promise<unknown>;
  };
}

declare global {
  interface Window {
    MP_SDK?: {
      connect(iframe: HTMLIFrameElement, key: string, version: string): Promise<ShowcaseSdk>;
    };
  }
}

const SDK_SCRIPT = "https://static.matterport.com/showcase-sdk/latest.js";

export function embedUrl(modelId: string, key: string): string {
  const q = new URLSearchParams({ m: modelId, play: "1", qs: "1", help: "0", applicationKey: key });
  return `https://my.matterport.com/show/?${q.toString()}`;
}

function loadScript(): Promise<void> {
  if (window.MP_SDK) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = SDK_SCRIPT;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load the Matterport SDK script"));
    document.head.appendChild(s);
  });
}

export async function connectShowcase(
  iframe: HTMLIFrameElement,
  key: string,
): Promise<ShowcaseSdk> {
  await loadScript();
  if (!window.MP_SDK) throw new Error("Matterport SDK missing");
  return window.MP_SDK.connect(iframe, key, "3.10");
}

/** Call onIds with the sweep ids of the model; the returned function cancels the subscription. */
export function watchSweeps(sdk: ShowcaseSdk, onIds: (ids: string[]) => void): () => void {
  const sub = sdk.Sweep.data.subscribe({
    onCollectionUpdated(c) {
      onIds(Object.keys(c));
    },
  });
  return () => sub.cancel();
}

/** Fly to the pose. Returns whether the model's own sweep was used or a stand-in. */
export async function flyToPose(
  sdk: ShowcaseSdk,
  call: SdkMoveTo,
  available: string[],
): Promise<{ stand: boolean } | null> {
  const pick = pickSweep(call.sweepId, available);
  if (!pick) return null;
  await sdk.Sweep.moveTo(pick.id, call.options);
  return { stand: pick.stand };
}
