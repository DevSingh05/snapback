import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { cancel, disconnect, fakeSdk } = vi.hoisted(() => {
  const cancel = vi.fn();
  const disconnect = vi.fn();
  return {
    cancel,
    disconnect,
    fakeSdk: {
      disconnect,
      Sweep: { moveTo: vi.fn(), data: { subscribe: () => ({ cancel }) } },
    },
  };
});

vi.mock("./showcase", async (orig) => ({
  ...(await orig<typeof import("./showcase")>()),
  connectShowcase: vi.fn().mockResolvedValue(fakeSdk),
}));

import { TwinView } from "./TwinPage";

describe("TwinView live mode", () => {
  it("cancels the sweep subscription and disconnects the SDK on unmount", async () => {
    const { unmount, findByText } = render(<TwinView caseId="fx-7Q2M" sdkKey="k" modelId="m" />);
    await findByText("Model ready");
    unmount();
    await waitFor(() => expect(cancel).toHaveBeenCalledOnce());
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
