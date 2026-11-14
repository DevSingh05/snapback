import { Suspense, lazy, useEffect, useState } from "react";

import { InvestigatePage } from "./investigate/InvestigatePage";
import { ConfirmPage } from "./office/ConfirmPage";
import { CardPage } from "./pages/CardPage";
import { ReplayIndexPage } from "./replay/ReplayIndexPage";
import { ReplayNav } from "./replay/ReplayNav";
import { ReplayPage } from "./replay/ReplayPage";
import { TourPage } from "./tour/TourPage";
import { TourPrepPage } from "./tourprep/TourPrepPage";
import { TracePage } from "./trace/TracePage";
import { TwinPage } from "./twin/TwinPage";
import { UploadPage } from "./upload/UploadPage";

// The city map loads on its own route only: its chunk (and MapLibre) never reaches the home page.
const MapPage = lazy(() => import("./map/MapPage"));

type Route =
  | { name: "map" }
  | { name: "result"; id: string }
  | { name: "trace"; id: string }
  | { name: "twin"; id: string }
  | { name: "verify"; id: string }
  | { name: "replay"; slug: string }
  | { name: "tour"; propertyId: string }
  | { name: "prep-case"; id: string }
  | { name: "prep-place"; propertyId: string }
  | { name: "confirm" }
  | { name: "investigate" }
  | { name: "replays" }
  | { name: "home" };

export function matchRoute(path: string): Route {
  if (/^\/map\/?$/.test(path)) return { name: "map" };
  if (/^\/confirm\/?$/.test(path)) return { name: "confirm" };
  if (/^\/investigate\/?$/.test(path)) return { name: "investigate" };
  if (/^\/replay\/?$/.test(path)) return { name: "replays" };
  const replay = /^\/replay\/([A-Za-z0-9_-]+)\/?$/.exec(path);
  if (replay?.[1]) return { name: "replay", slug: replay[1] };
  const tour = /^\/tour\/([A-Za-z0-9_.:-]+)\/?$/.exec(path);
  if (tour?.[1]) return { name: "tour", propertyId: tour[1] };
  const prepCase = /^\/case\/([A-Za-z0-9_-]+)\/prep\/?$/.exec(path);
  if (prepCase?.[1]) return { name: "prep-case", id: prepCase[1] };
  const prepPlace = /^\/prep\/place\/([A-Za-z0-9_.:-]+)\/?$/.exec(path);
  if (prepPlace?.[1]) return { name: "prep-place", propertyId: prepPlace[1] };
  const trace = /^\/case\/([A-Za-z0-9_-]+)\/trace\/?$/.exec(path);
  if (trace?.[1]) return { name: "trace", id: trace[1] };
  const twin = /^\/case\/([A-Za-z0-9_-]+)\/twin\/?$/.exec(path);
  if (twin?.[1]) return { name: "twin", id: twin[1] };
  const result = /^\/case\/([A-Za-z0-9_-]+)\/?$/.exec(path);
  if (result?.[1]) return { name: "result", id: result[1] };
  const verify = /^\/c\/([A-Za-z0-9_-]+)\/?$/.exec(path);
  if (verify?.[1]) return { name: "verify", id: verify[1] };
  return { name: "home" };
}

// Two routes and no router library: /case/:id is the renter's result page and /c/:id is the
// verify page the QR code points to. Both read the same Card.
export default function App() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const route = matchRoute(path);
  if (route.name === "map") {
    return (
      <main className="shell-map">
        <Suspense fallback={<p className="map-wait">Opening the city...</p>}>
          <MapPage />
        </Suspense>
      </main>
    );
  }
  return (
    <main className="shell">
      <ReplayNav />
      {route.name === "home" ? (
        <UploadPage />
      ) : route.name === "confirm" ? (
        <ConfirmPage />
      ) : route.name === "investigate" ? (
        <InvestigatePage />
      ) : route.name === "replays" ? (
        <ReplayIndexPage />
      ) : route.name === "replay" ? (
        <ReplayPage key={route.slug} slug={route.slug} />
      ) : route.name === "tour" ? (
        <TourPage
          key={`tour-${route.propertyId}-${window.location.search}`}
          target={{
            propertyId: route.propertyId,
            planKey: new URLSearchParams(window.location.search).get("plan_key"),
            caseId: new URLSearchParams(window.location.search).get("case"),
            mode:
              new URLSearchParams(window.location.search).get("where") === "photos"
                ? "elsewhere"
                : "claimed",
          }}
        />
      ) : route.name === "prep-case" ? (
        <TourPrepPage
          key={`prep-${route.id}`}
          target={{ kind: "case", caseId: route.id }}
          back={`/case/${route.id}`}
        />
      ) : route.name === "prep-place" ? (
        <TourPrepPage
          key={`prep-place-${route.propertyId}-${window.location.search}`}
          target={{
            kind: "place",
            propertyId: route.propertyId,
            planKey: new URLSearchParams(window.location.search).get("plan_key"),
          }}
          back="/"
        />
      ) : route.name === "trace" ? (
        <TracePage key={`trace-${route.id}`} caseId={route.id} />
      ) : route.name === "twin" ? (
        <TwinPage key={route.id} caseId={route.id} />
      ) : (
        <CardPage key={`${route.name}-${route.id}`} caseId={route.id} variant={route.name} />
      )}
    </main>
  );
}
