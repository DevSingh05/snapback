import { apiFetch, dataMode, saveCaseReadToken, saveCaseToken } from "../api";

export type RunCase = (caseCode: string) => Promise<string>;

// "Run this case": POST /cases naming the replay's staged case. The server accepts only the case
// id of a replay it serves, and answers with a real case whose card the page then opens.
export const runReplayCase: RunCase = async (caseCode) => {
  if (dataMode() === "fixture") throw new Error("No API is configured.");
  const body = new FormData();
  body.append("demo_case", caseCode);
  const res = await apiFetch("/cases", { method: "POST", body });
  if (!res.ok) throw new Error(`The server answered ${res.status}.`);
  const made = (await res.json()) as { case_id: string; token: string; read_token?: string | null };
  saveCaseToken(made.case_id, made.token);
  if (made.read_token) saveCaseReadToken(made.case_id, made.read_token);
  return made.case_id;
};

export function openCase(caseId: string) {
  window.history.pushState({}, "", `/case/${encodeURIComponent(caseId)}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
