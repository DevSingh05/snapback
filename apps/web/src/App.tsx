import { useEffect, useState } from "react";

import { CardPage } from "./pages/CardPage";
import { ReplayPage } from "./replay/ReplayPage";
import { TracePage } from "./trace/TracePage";
import { TwinPage } from "./twin/TwinPage";
import { UploadPage } from "./upload/UploadPage";

type Route =
  | { name: "result"; id: string }
  | { name: "trace"; id: string }
  | { name: "twin"; id: string }
  | { name: "verify"; id: string }
  | { name: "replay"; slug: string }
  | { name: "home" };

export function matchRoute(path: string): Route {
  const replay = /^\/replay\/([A-Za-z0-9_-]+)\/?$/.exec(path);
  if (replay?.[1]) return { name: "replay", slug: replay[1] };
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
  return (
    <main className="shell">
      {route.name === "home" ? (
        <UploadPage />
      ) : route.name === "replay" ? (
        <ReplayPage key={route.slug} slug={route.slug} />
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
