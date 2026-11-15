import { Suspense, lazy, useEffect, useState } from "react";

import { InvestigatePage } from "./investigate/InvestigatePage";
import { ConfirmPage } from "./office/ConfirmPage";
import { OneBox } from "./home/OneBox";
import { CardPage } from "./pages/CardPage";
import { ReplayIndexPage } from "./replay/ReplayIndexPage";
import { ReplayPage } from "./replay/ReplayPage";
import { AppShell, type Section } from "./shell/AppShell";
import { FinderPage } from "./shell/FinderPage";
import { ListingsPage } from "./shell/ListingsPage";
import { loadPrefs, tabOf } from "./shell/prefs";
import { StoriesPage } from "./stories/StoriesPage";
import { TourPage } from "./tour/TourPage";
import { TourPrepPage } from "./tourprep/TourPrepPage";
import { TracePage } from "./trace/TracePage";
import { TwinPage } from "./twin/TwinPage";

// The city map loads on its own route only: its chunk (and MapLibre) never reaches the home page.
const MapPage = lazy(() => import("./map/MapPage"));

type Route =
  | { name: "map" }
  | { name: "listings" }
  | { name: "finder" }
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
  | { name: "stories" }
  | { name: "proof-room" }
  | { name: "home" };

// /proof-room?case=<id> is the stable address for "watch your check team" (iMessage links to
// it). The team works beside the 3D twin, so it lands there; with no case it lands on Home.
export function proofRoomTarget(search: string): string {
  const id = new URLSearchParams(search).get("case") ?? "";
  return /^[A-Za-z0-9_-]+$/.test(id) ? `/case/${id}/twin` : "/";
}

export function matchRoute(path: string): Route {
  if (/^\/proof-room\/?$/.test(path)) return { name: "proof-room" };
  if (/^\/map\/?$/.test(path)) return { name: "map" };
  if (/^\/listings\/?$/.test(path)) return { name: "listings" };
  if (/^\/finder\/?$/.test(path)) return { name: "finder" };
  if (/^\/confirm\/?$/.test(path)) return { name: "confirm" };
  if (/^\/stories\/?$/.test(path)) return { name: "stories" };
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
  // The site's root opens on Home. Only a tab in the bar can open first (prefs.clean), so an
  // old saved choice never lands anyone on a page the front cut took out of the bar.
  useEffect(() => {
    const first = loadPrefs().first;
    if (window.location.pathname === "/" && first !== "home")
      window.location.replace(tabOf(first).href);
  }, []);
  const toTwin = route.name === "proof-room";
  useEffect(() => {
    if (toTwin) window.location.replace(proofRoomTarget(window.location.search));
  }, [toTwin]);
  const section: Section | "stories" | null =
    route.name === "home"
      ? "home"
      : route.name === "stories"
        ? "stories"
        : route.name === "map"
          ? "map"
          : route.name === "listings"
            ? "listings"
            : route.name === "finder"
              ? "finder"
              : route.name === "replays" || route.name === "replay"
                ? "replays"
                : null;
  // Inside a place, the bar says where you are.
  const here = window.location.pathname + window.location.search;
  const context =
    route.name === "tour"
      ? { label: "Walk", href: here }
      : route.name === "prep-case" || route.name === "prep-place"
        ? { label: "Tour prep", href: here }
        : route.name === "result" || route.name === "verify"
          ? { label: "Report", href: here }
          : null;
  if (toTwin) return null;
  if (route.name === "map") {
    return (
      <AppShell section="map">
        <main className="shell-map">
          <Suspense fallback={<p className="map-wait">Opening the city...</p>}>
            <MapPage />
          </Suspense>
        </main>
      </AppShell>
    );
  }
  return (
    <AppShell section={section} context={context}>
      <main className={route.name === "home" ? "shell shell-home" : "shell"}>
        {route.name === "home" ? (
          <OneBox />
        ) : route.name === "listings" ? (
          <ListingsPage />
        ) : route.name === "finder" ? (
          <FinderPage />
        ) : route.name === "stories" ? (
          <StoriesPage />
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
    </AppShell>
  );
}
