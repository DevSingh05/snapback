import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";
import { TwinView } from "./TwinPage";

describe("TwinView without a Matterport key", () => {
  it("shows the placeholder and a FIXTURE chip, and still mounts the trace slot", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByText(/3D view needs a Matterport key/)).toBeInTheDocument();
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("FIXTURE");
    expect(screen.getByTestId("trace-slot")).toBeInTheDocument();
  });

  it("lists the located photo from the fixture and offers fly-to for it", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByRole("button", { name: /Fly to photo l1/ })).toBeInTheDocument();
  });
});

describe("TwinView photo landing", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubReducedMotion(reduce: boolean) {
    vi.stubGlobal(
      "matchMedia",
      (q: string) =>
        ({
          matches: reduce && q.includes("reduce"),
          media: q,
          addEventListener: () => {},
          removeEventListener: () => {},
        }) as unknown as MediaQueryList,
    );
  }

  it("lands the fixture pose with the Taken here line and no 3D key (static fallback)", async () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(await screen.findByText("Taken here: Living room")).toBeInTheDocument();
    expect(screen.getByTestId("static-plan")).toBeInTheDocument();
    expect(screen.getByTestId("view-cone")).toBeInTheDocument();
    expect(screen.getByTestId("photo-overlay")).toBeInTheDocument();
  });

  it("reduced motion: the photo is at landed opacity at once, with no flight", async () => {
    stubReducedMotion(true);
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-motion", "reduced");
    await waitFor(() =>
      expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.6" }),
    );
    expect(screen.getByTestId("photo-overlay")).not.toHaveAttribute("data-flying");
  });

  it("still finishes landing under StrictMode's mount, unmount, mount", async () => {
    stubReducedMotion(true);
    render(
      <StrictMode>
        <TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />
      </StrictMode>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.6" }),
    );
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-phase", "landed");
  });

  it("a located photo with no pose is Taken here, with no cone and a no-angle note", async () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    await userEvent.click(screen.getByRole("button", { name: /Fly to photo l2/ }));
    expect(await screen.findByText("Taken here: this building")).toBeInTheDocument();
    expect(screen.getByText("No camera angle for this photo")).toBeInTheDocument();
    expect(screen.queryByText("Not found in this building")).toBeNull();
    expect(screen.queryByTestId("view-cone")).toBeNull();
    expect(screen.queryByTestId("photo-overlay")).toBeNull();
  });

  it("a photo the matcher did not place reads Not found in this building", async () => {
    const l = {
      ...hold.locate,
      photos: [{ photo_id: "l1", status: "not_located" }],
    } as unknown as LocateResult;
    render(<TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={l} liveLocate />);
    expect(await screen.findByText("Not found in this building")).toBeInTheDocument();
  });

  it("shows no fixture room name for a live pose without labels", async () => {
    render(
      <TwinView
        caseId="x"
        sdkKey={undefined}
        modelId={undefined}
        locate={{ ...hold.locate, case_id: "live" } as unknown as LocateResult}
        liveLocate
      />,
    );
    expect(await screen.findByText("Taken here")).toBeInTheDocument();
    expect(screen.queryByText(/Living room/)).toBeNull();
  });

  it("keeps the trace as a collapsed strip", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByRole("button", { name: /Agent trace/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("ignores a live LocateResult unless the flag is on", () => {
    const live = { ...hold.locate, case_id: "live", poses: {} } as unknown as LocateResult;
    const { unmount } = render(
      <TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={live} />,
    );
    expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("FIXTURE");
    unmount();
    render(<TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={live} liveLocate />);
    expect(screen.getAllByTestId("source-chip")[1]).toHaveTextContent("LIVE");
  });
});
