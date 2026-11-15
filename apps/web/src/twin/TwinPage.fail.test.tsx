import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("./showcase", async (orig) => ({
  ...(await orig<typeof import("./showcase")>()),
  connectShowcase: vi.fn().mockRejectedValue(new Error("Could not load the Matterport SDK script")),
}));

import { TwinView } from "./TwinPage";

describe("TwinView when the SDK fails with a key present", () => {
  it("labels the model chip UNAVAILABLE and the plan Schematic, and still lands the photo", async () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey="k" modelId="m" />);
    await waitFor(() =>
      expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("UNAVAILABLE"),
    );
    expect(screen.getAllByTestId("source-chip")[0]).not.toHaveTextContent("LIVE");
    expect(screen.getByText("Schematic")).toBeInTheDocument();
    expect(screen.getByTestId("static-plan")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "1" }));
  });
});
