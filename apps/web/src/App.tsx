import { useEffect, useState } from "react";

import { CardPage } from "./pages/CardPage";

type Route = { name: "result"; id: string } | { name: "verify"; id: string } | { name: "home" };

export function matchRoute(path: string): Route {
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
        <div className="card-page notice">
          <span className="wordmark">SNAPBACK</span>
          <h1>Check any rental before you pay.</h1>
          <p>
            Open a result at <span className="mono">/case/7Q2M</span> or a verify page at{" "}
            <span className="mono">/c/7Q2M</span>.
          </p>
        </div>
      ) : (
        <CardPage key={`${route.name}-${route.id}`} caseId={route.id} variant={route.name} />
      )}
    </main>
  );
}
