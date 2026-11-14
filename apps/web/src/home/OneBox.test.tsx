import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CreateCase } from "../upload/api";
import { EXAMPLES, FB_ASK, OneBox } from "./OneBox";

const AD =
  "Sunny 2 bed 2 bath in Midtown, $1,350/month. I'm abroad so I can't show it, send the $600 deposit by Zelle.";

function made(): CreateCase {
  return vi.fn(async () => ({
    case_id: "7Q2M",
    source: "fixture" as const,
    challenge_text: "Send a photo of the door with today's date, please.",
  }));
}

const box = () => screen.getByLabelText(/paste an ad, a link, or say what you need/i);

async function say(user: ReturnType<typeof userEvent.setup>, words: string) {
  await user.type(box(), words);
  await user.click(screen.getByRole("button", { name: /^send$/i }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("Home is one box", () => {
  it("opens on one input, four starters and no form", async () => {
    render(<OneBox mode="fixture" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/ask before you pay/i);
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/max rent/i)).not.toBeInTheDocument();
    const starters = within(screen.getByRole("list", { name: "Try one" })).getAllByRole("button");
    expect(starters.map((b) => b.textContent)).toEqual([...EXAMPLES]);
    expect(screen.getByRole("button", { name: /add screenshots/i })).toBeInTheDocument();
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("FIXTURE");
  });

  it("an empty send says what to do and starts nothing", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} />);
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
    await user.type(box(), "   {Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(/paste an ad, or add screenshots/i);
    expect(createCase).not.toHaveBeenCalled();
  });
});

describe("routing each message, shown honestly", () => {
  it("pasted ad text starts the check, and the verdict lands inline after your OK", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} waitingMs={0} />);
    await say(user, AD);

    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    expect(screen.getByTestId("ob-switch")).toHaveTextContent("I'm looking for a place");
    await waitFor(() => expect(createCase).toHaveBeenCalledTimes(1));
    expect(createCase).toHaveBeenCalledWith(
      expect.objectContaining({ link: null, text: AD, files: [] }),
    );

    // Nothing goes to the poster without the renter's yes.
    expect(await screen.findByLabelText(/message to send/i)).toHaveValue(
      "Send a photo of the door with today's date, please.",
    );
    await user.click(screen.getByRole("button", { name: /i approve it/i }));

    const verdict = await screen.findByTestId("ob-verdict");
    expect(verdict).toHaveTextContent("Hold off for now");
    expect(verdict).toHaveTextContent("Code set this verdict");
    expect(within(verdict).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(within(verdict).getByRole("link", { name: "Walk it first" })).toHaveAttribute(
      "href",
      "/case/7Q2M/twin",
    );
    expect(within(verdict).getByRole("link", { name: "Open the full result" })).toHaveAttribute(
      "href",
      "/case/7Q2M",
    );
    // Answer first: the red flag leads, the rest is one tap below.
    expect(within(verdict).getAllByRole("term")[0]).toHaveTextContent("Payment ask");
    await user.click(within(verdict).getByRole("button", { name: /how we know: all 5 checks/i }));
    expect(within(verdict).getAllByRole("term")).toHaveLength(5);
  });

  it("a listing URL starts the check with the link", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} waitingMs={0} />);
    await say(user, "zillow.com/homedetails/123");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    await waitFor(() =>
      expect(createCase).toHaveBeenCalledWith(
        expect.objectContaining({ link: "https://zillow.com/homedetails/123", text: null }),
      ),
    );
    await user.click(await screen.findByRole("button", { name: /skip this, show the result/i }));
    expect(await screen.findByTestId("ob-verdict")).toHaveTextContent("Hold off for now");
  });

  it("a wish goes to the Finder; without the Finder service, code lists places and says so", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} />);
    await say(user, "find me a 1 bed under 1500");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Finding places");
    const places = await screen.findByTestId("ob-places");
    expect(places).toHaveTextContent("Places for 1+ bed, under $1,500");
    expect(places).toHaveTextContent(/code read your words/i);
    expect(within(places).getAllByTestId("ob-pick").length).toBeGreaterThan(0);
    expect(within(places).getAllByText("Picked by our rules").length).toBeGreaterThan(0);
    expect(within(places).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(createCase).not.toHaveBeenCalled();
  });

  it("asks for the max rent in the thread, with quick replies, instead of a budget form", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" />);
    await say(user, "looking for a 1 bed near downtown");
    const ask = await screen.findByText("What's your max rent a month?");
    expect(ask.closest("li")).toHaveTextContent("Picked by our rules");
    // No form appears: one text box, no number fields, no budget inputs.
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/max rent/i)).not.toBeInTheDocument();
    const replies = within(screen.getByRole("list", { name: "Quick replies" })).getAllByRole(
      "button",
    );
    expect(replies.map((r) => r.textContent)).toEqual([
      "$1,200",
      "$1,500",
      "$2,000",
      "$2,500",
      "No limit",
    ]);
    await user.click(screen.getByRole("button", { name: "$1,500" }));
    expect(await screen.findByTestId("ob-places")).toHaveTextContent("under $1,500");
    // Known now: the next wish does not ask again.
    await say(user, "find me a studio");
    await waitFor(() => expect(screen.getAllByTestId("ob-places")).toHaveLength(2));
    expect(screen.getAllByText("What's your max rent a month?")).toHaveLength(1);
  });

  it("a typed amount answers the open budget question", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" />);
    await say(user, "looking for a 1 bed near downtown");
    await screen.findByText("What's your max rent a month?");
    await say(user, "1800");
    expect(await screen.findByTestId("ob-places")).toHaveTextContent("under $1,800");
  });

  it("the switch re-runs the same words the other way", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} waitingMs={0} />);
    await say(user, "2 bed under $2,000 with parking");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Finding places");
    await user.click(screen.getByTestId("ob-switch"));
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    await waitFor(() => expect(createCase).toHaveBeenCalledTimes(1));
  });

  it("screenshots alone start the check; a PDF is refused by name", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} waitingMs={0} />);
    const input = document.getElementById("photos") as HTMLInputElement;
    await user.upload(input, new File(["x"], "lease.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("lease.pdf is not a photo");
    await user.upload(input, new File(["x"], "ad.png", { type: "image/png" }));
    expect(screen.getByRole("list", { name: "Added screenshots" })).toHaveTextContent("ad.png");
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    expect(screen.getByTestId("ob-you")).toHaveTextContent("1 screenshot: ad.png");
    await waitFor(() =>
      expect(createCase).toHaveBeenCalledWith(
        expect.objectContaining({ files: [expect.objectContaining({ name: "ad.png" })] }),
      ),
    );
  });

  it("opens any view by asking, and a check request with nothing to check asks for the ad", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" />);
    await say(user, "show me on the map");
    expect(screen.getByTestId("ob-open")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the map" })).toHaveAttribute("href", "/map");
    await user.click(screen.getByRole("button", { name: "New conversation" }));
    await user.click(screen.getByRole("button", { name: "Is this landlord real?" }));
    expect(await screen.findByText(/paste the ad's link or its text here/i)).toBeInTheDocument();
  });

  it("a Facebook link is never fetched: it asks for the text and photos, then checks those", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} waitingMs={0} />);
    await say(user, "https://www.facebook.com/marketplace/item/123456789/");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking a Facebook ad");
    expect(await screen.findByText(FB_ASK)).toBeInTheDocument();
    expect(createCase).not.toHaveBeenCalled();
    await say(user, `https://www.facebook.com/marketplace/item/123456789/ ${AD}`);
    await waitFor(() => expect(createCase).toHaveBeenCalledTimes(1));
    // Only the renter's words go to the check; the Facebook address is dropped.
    expect(createCase).toHaveBeenCalledWith(expect.objectContaining({ link: null, text: AD }));
  });

  it("a server error on the check is shown in the thread, nothing sent", async () => {
    const user = userEvent.setup();
    const createCase: CreateCase = vi.fn(async () => {
      throw new Error("The server answered 502.");
    });
    render(<OneBox mode="fixture" createCase={createCase} />);
    await say(user, "zillow.com/homedetails/123");
    expect(await screen.findByTestId("ob-check-error")).toHaveTextContent("502");
    expect(screen.getByTestId("ob-check-error")).toHaveTextContent("Nothing was sent");
  });
});
