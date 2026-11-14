import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TwinView } from "./TwinPage";

describe("TwinView without a Matterport key", () => {
  it("shows the placeholder and a FIXTURE chip, and still mounts the trace slot", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByText(/3D view needs a Matterport key/)).toBeInTheDocument();
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(screen.getByTestId("trace-slot")).toBeInTheDocument();
  });

  it("lists the located photo from the fixture and offers fly-to for it", () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey={undefined} modelId={undefined} />);
    expect(screen.getByRole("button", { name: /Fly to photo l1/ })).toBeInTheDocument();
  });
});
