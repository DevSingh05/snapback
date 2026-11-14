import { useEffect, useState } from "react";

type Health = { status: string; data_source: "live" | "fixture" };

// Skeleton only: proves the web app can reach the API and shows which data source is active.
// Every real screen must carry the same LIVE / FIXTURE label.
export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/healthz")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((body: Health) => setHealth(body))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  let apiLine = "checking…";
  if (health) apiLine = `${health.status} · ${health.data_source.toUpperCase()}`;
  else if (error) apiLine = `unreachable (${error})`;

  return (
    <main>
      <h1>SNAPBACK</h1>
      <p>Skeleton only. Nothing on this page is a product screen yet.</p>
      <p>API: {apiLine}</p>
    </main>
  );
}
