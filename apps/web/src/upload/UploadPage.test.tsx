import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CreateCase } from "./api";
import { UploadPage } from "./UploadPage";

const made = {
  case_id: "7Q2M",
  source: "fixture" as const,
  challenge_text: "Send a photo of the door, please.",
};

function setup(createCase: CreateCase = vi.fn().mockResolvedValue(made)) {
  const navigate = vi.fn();
  render(<UploadPage createCase={createCase} navigate={navigate} checkingMs={0} waitingMs={0} />);
  return { createCase, navigate };
}

describe("UploadPage", () => {
  it("submits a link, shows the approval step, and only navigates after approval", async () => {
    const user = userEvent.setup();
    const { createCase, navigate } = setup();

    await user.type(
      screen.getByLabelText(/listing link or text/i),
      "https://zillow.com/homedetails/1",
    );
    await user.click(screen.getByRole("button", { name: /check this listing/i }));

    expect(createCase).toHaveBeenCalledWith({
      link: "https://zillow.com/homedetails/1",
      text: null,
      files: [],
    });
    const message = await screen.findByLabelText(/message to forward/i);
    expect(message).toHaveValue("Send a photo of the door, please.");
    expect(navigate).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /i approve it/i }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("7Q2M"));
  });

  it("skipping the live check goes to the case without sending", async () => {
    const user = userEvent.setup();
    const { navigate } = setup();
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await user.click(await screen.findByRole("button", { name: /skip the live check/i }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("7Q2M"));
  });

  it("an empty submit says how to fix it and calls nothing", async () => {
    const user = userEvent.setup();
    const { createCase } = setup();
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /paste a listing link or add screenshots/i,
    );
    expect(createCase).not.toHaveBeenCalled();
  });

  it("rejects a PDF with a message that names it", async () => {
    const user = userEvent.setup({ applyAccept: false });
    setup();
    const pdf = new File(["x"], "lease.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText(/screenshots or photos/i), pdf);
    expect(await screen.findByRole("alert")).toHaveTextContent(/lease\.pdf is not a photo/);
  });

  it("accepts screenshots alone, lists them, and removes one", async () => {
    const user = userEvent.setup();
    const { createCase } = setup();
    const png = new File(["x"], "listing.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/screenshots or photos/i), png);
    expect(screen.getByText("listing.png")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove listing\.png/i }));
    expect(screen.queryByText("listing.png")).not.toBeInTheDocument();
    await user.upload(screen.getByLabelText(/screenshots or photos/i), png);
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await screen.findByLabelText(/message to forward/i);
    expect(createCase).toHaveBeenCalledWith({ link: null, text: null, files: [png] });
  });

  it("shows the server error and returns to the form on retry", async () => {
    const user = userEvent.setup();
    setup(vi.fn().mockRejectedValue(new Error("The server answered 500. Try again in a moment.")));
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/server answered 500/);
    await user.click(screen.getByRole("button", { name: /back to the form/i }));
    expect(screen.getByLabelText(/listing link or text/i)).toBeInTheDocument();
  });

  it("shows the FIXTURE chip once the case exists", async () => {
    const user = userEvent.setup();
    setup();
    await user.type(screen.getByLabelText(/listing link or text/i), "zillow.com/x/1");
    await user.click(screen.getByRole("button", { name: /check this listing/i }));
    await screen.findByLabelText(/message to forward/i);
    expect(screen.getByTestId("source-chip")).toHaveTextContent("FIXTURE");
  });
});
