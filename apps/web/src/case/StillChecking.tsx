// The quiet stand-in for a report section whose read answered 202: the check is still running.
// One plain line, no spinner and no error; the section replaces it when its data lands.
export function StillChecking({ testId }: { testId: string }) {
  return (
    <p className="case-checking ui-mono" role="status" data-testid={testId}>
      Still checking…
    </p>
  );
}
