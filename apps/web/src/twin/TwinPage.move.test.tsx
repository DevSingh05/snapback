import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { fakeSdk } = vi.hoisted(() => ({
  fakeSdk: {
    disconnect: vi.fn(),
    Sweep: {
      moveTo: vi.fn().mockRejectedValue(new Error("moveTo failed")),
      data: {
        subscribe: (o: { onCollectionUpdated(c: Record<string, unknown>): void }) => {
          o.onCollectionUpdated({ "fx-sweep-03": {} });
          return { cancel: vi.fn() };
        },
      },
    },
  },
}));

vi.mock("./showcase", async (orig) => ({
  ...(await orig<typeof import("./showcase")>()),
  connectShowcase: vi.fn().mockResolvedValue(fakeSdk),
}));

import { TwinView } from "./TwinPage";

describe("TwinView when the 3D move rejects", () => {
  it("still lands the photo on the static view instead of staying at opacity 0", async () => {
    render(<TwinView caseId="fx-7Q2M" sdkKey="k" modelId="m" />);
    await waitFor(() =>
      expect(screen.getByTestId("photo-overlay")).toHaveStyle({ opacity: "0.6" }),
    );
    expect(screen.getByText("moveTo failed")).toBeInTheDocument();
    expect(fakeSdk.Sweep.moveTo).toHaveBeenCalled();
  });
});
