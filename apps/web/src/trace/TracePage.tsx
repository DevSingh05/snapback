import { TracePanel } from "./TracePanel";

// Standalone route /case/:id/trace. T2's twin page mounts <TracePanel caseId=... /> directly.
export function TracePage({ caseId }: { caseId: string }) {
  return (
    <div className="card-page trace-page">
      <div className="masthead">
        <span className="wordmark">SNAPBACK</span>
        <span className="mono">
          Case <span className="case-id">{caseId}</span>
        </span>
      </div>
      <TracePanel caseId={caseId} />
    </div>
  );
}
