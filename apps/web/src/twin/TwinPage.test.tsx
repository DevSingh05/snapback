import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import hold from "../../../../fixtures/contracts/module_evidence_hold.json";
import type { LocateResult } from "../contracts";
import { TwinView, demoFromSearch } from "./TwinPage";

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
      expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.45" }),
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
      expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.45" }),
    );
    expect(screen.getByTestId("photo-landing")).toHaveAttribute("data-phase", "landed");
  });

  it("a located photo with no pose is Taken here, with no cone and a no-angle note", async () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    await userEvent.click(screen.getByRole("button", { name: /Fly to photo l2/ }));
    expect(await screen.findByText("Taken here: this home")).toBeInTheDocument();
    expect(screen.getByText("No camera angle for this photo")).toBeInTheDocument();
    expect(screen.queryByText("Could not place this photo")).toBeNull();
    expect(screen.queryByTestId("view-cone")).toBeNull();
    expect(screen.queryByTestId("photo-overlay")).toBeNull();
  });

  it("a photo the matcher did not place reads Could not place this photo", async () => {
    const l = {
      ...hold.locate,
      photos: [{ photo_id: "l1", status: "not_located" }],
    } as unknown as LocateResult;
    render(<TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={l} liveLocate />);
    expect(await screen.findByText("Could not place this photo")).toBeInTheDocument();
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

  it("a live photo in the claimed property's second twin reads Taken here with its own room", async () => {
    const l = {
      ...hold.locate,
      case_id: "live",
      photos: [
        {
          photo_id: "l1",
          status: "located_in_claimed",
          model_id: "fx-model-b",
          matched_model_id: "fx-model-b",
          matched_property_id: "fx-prop-1",
          room_label: "Kitchen",
        },
      ],
    } as unknown as LocateResult;
    render(<TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={l} liveLocate />);
    expect(await screen.findByText("Taken here: Kitchen")).toBeInTheDocument();
    expect(screen.queryByText("The listing says here.")).toBeNull();
  });

  it("elsewhere inside the claimed property, or with no matched property, shows no second building", () => {
    const l = {
      ...hold.locate,
      case_id: "live",
      photos: [
        { photo_id: "l1", status: "located_elsewhere", matched_property_id: "fx-prop-1" },
        { photo_id: "l2", status: "located_elsewhere", matched_property_id: null },
      ],
    } as unknown as LocateResult;
    render(<TwinView caseId="x" sdkKey={undefined} modelId={undefined} locate={l} liveLocate />);
    expect(screen.queryByText("The listing says here.")).toBeNull();
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
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

describe("TwinView aerial proof", () => {
  it("shows one tile when the photo is in the claimed building", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.queryByTestId("aerial-distance")).toBeNull();
    expect(screen.queryByText("The listing says here.")).toBeNull();
  });

  it("shows both buildings and the distance when a photo is located elsewhere", () => {
    const elsewhere = {
      ...(hold.locate as unknown as LocateResult),
      photos: [
        {
          photo_id: "l1",
          status: "located_elsewhere",
          model_id: "fx-model-b",
          matched_property_id: "fx-prop-2",
        },
      ],
    } as LocateResult;
    render(
      <TwinView
        caseId="fx-7Q2M"
        sdkKey={undefined}
        modelId={undefined}
        locate={elsewhere}
        liveLocate
      />,
    );
    expect(screen.getByText("The listing says here.")).toBeInTheDocument();
    expect(screen.getByText("This photo was taken here.")).toBeInTheDocument();
    expect(screen.getByTestId("aerial-distance")).toHaveTextContent("0.4 miles away");
  });
});

describe("TwinView demo=copied", () => {
  it("parses the demo flag from the query string", () => {
    expect(demoFromSearch("?demo=copied")).toBe("copied");
    expect(demoFromSearch("?demo=other")).toBeUndefined();
    expect(demoFromSearch("")).toBeUndefined();
  });

  it("shows the two-building view from fixtures, labelled FIXTURE throughout", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} demo="copied" />);
    expect(screen.getByText("The listing says here.")).toBeInTheDocument();
    expect(screen.getByTestId("aerial-distance")).toHaveTextContent("0.4 miles away");
    for (const chip of screen.getAllByTestId("source-chip"))
      expect(chip).toHaveTextContent("FIXTURE");
  });
});
