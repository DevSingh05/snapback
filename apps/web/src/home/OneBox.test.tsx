import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import cardHold from "../../../../fixtures/contracts/card_hold.json";
import type { Card } from "../contracts";
import type { CreateCase } from "../upload/api";
import { EXAMPLES, FB_ASK, HOW, MEASURED, OneBox, VerdictView, sendLabel } from "./OneBox";

// The box's button names what it will do: it follows the routing of what is typed.
const SEND = /^(check it|find places|ask)$/i;

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
  await user.click(screen.getByRole("button", { name: SEND }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

describe("Home is one box", () => {
  it("opens on one input, two starters and no form", async () => {
    render(<OneBox mode="fixture" />);
    expect(screen.getAllByRole("textbox")).toHaveLength(1);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/max rent/i)).not.toBeInTheDocument();
    const starters = within(screen.getByRole("list", { name: "Try one" })).getAllByRole("button");
    expect(starters.map((b) => b.textContent)).toEqual([...EXAMPLES]);
    expect(screen.getByRole("button", { name: /add screenshots/i })).toBeInTheDocument();
    expect(screen.getAllByTestId("source-chip")[0]).toHaveTextContent("FIXTURE");
  });

  it("says the use case in the headline: send an ad before you pay, get a report", () => {
    render(<OneBox mode="fixture" />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Send a rental ad before you pay.");
    expect(h1).toHaveTextContent("Get a report: is this the real listing, and who do you call?");
  });

  it("says how it works in three lines, in order, above the box", () => {
    render(<OneBox mode="fixture" />);
    const how = screen.getByTestId("ob-how");
    expect(
      within(how)
        .getAllByRole("listitem")
        .map((li) => li.querySelector("b")!.textContent),
    ).toEqual(["Send the ad", "We check it", "You get a report"]);
    for (const step of HOW) expect(how).toHaveTextContent(step.text);
    expect(how.compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("the front cut: no walk or find prompt, no four-step strip, and no door to a hidden page", () => {
    render(<OneBox mode="fixture" />);
    expect(EXAMPLES).toEqual(["Paste the ad you were sent", "Is this landlord real?"]);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/Walk me through a place|Find me a 1 bed/);
    expect(screen.queryByTestId("how-it-works")).toBeNull();
    const hrefs = [...document.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    for (const hidden of ["/listings", "/map", "/finder", "/replay", "/investigate"])
      expect(hrefs, hidden).not.toContain(hidden);
    expect(hrefs).toContain("/stories");
  });

  it("the hero photo has alt text, and every sample photo is stamped as one", () => {
    render(<OneBox mode="fixture" />);
    const hero = screen.getByTestId("hero-photo");
    expect(hero).toHaveAttribute("alt", expect.stringMatching(/apartment building/i));
    // The sample report's proof pair: two stock photos, both stamped, and not the same picture.
    const samples = screen.getAllByTestId("sample-photo");
    expect(samples).toHaveLength(2);
    for (const s of samples) {
      expect(s).toHaveTextContent(/sample photo/i);
      expect(within(s).getByRole("img")).toHaveAttribute("alt", expect.stringMatching(/\w/));
    }
    const [ad, scan] = samples.map((s) => within(s).getByRole("img").getAttribute("src"));
    expect(ad).not.toBe(scan);
  });

  it("leads with checking an ad, and the box asks for the ad", () => {
    render(<OneBox mode="fixture" />);
    const starters = within(screen.getByRole("list", { name: "Try one" })).getAllByRole("listitem");
    expect(starters).toHaveLength(2);
    expect(starters[0]).toHaveTextContent("Paste the ad you were sent");
    expect(starters[1]).toHaveTextContent("Is this landlord real?");
    expect(box()).toHaveAttribute(
      "placeholder",
      expect.stringMatching(/^Paste the ad you were sent/),
    );
  });

  it("carries the one measured line, word for word, and no other figure of its own", () => {
    render(<OneBox mode="fixture" />);
    expect(screen.getByTestId("ob-measured").textContent).toBe(
      "Measured on 78 real listing photos: 43 of 48 placed in the right home, 0 in the wrong one, 0 of 30 decoys fooled it",
    );
    expect(MEASURED).not.toMatch(/right room|[–—]/);
  });

  it("the button names what the box will do, following the routing of what is typed", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" />);
    expect(screen.getByRole("button", { name: "Check it" })).toBeDisabled();
    await user.type(box(), "Find me a 1 bed under $1,500 near downtown");
    expect(screen.getByRole("button", { name: "Find places" })).toBeEnabled();
    await user.clear(box());
    await user.type(box(), "Is this landlord real?");
    expect(screen.getByRole("button", { name: "Check it" })).toBeEnabled();
    await user.clear(box());
    await user.type(box(), "Is it ok to pay a deposit by Zelle?");
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
    expect(sendLabel("https://example.com/listing/1", 0, false)).toBe("Check it");
    expect(sendLabel("", 2, false)).toBe("Check it");
  });

  it("the sample case shows the fixture card's own verdict and opens it through the box", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" createCase={made()} checkingMs={0} />);
    const sample = screen.getByTestId("ob-sample");
    expect(sample).toHaveTextContent("Sample report 7Q2M");
    expect(sample).toHaveTextContent("Hold off for now");
    expect(within(sample).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    // Proof, not features: the ad's photo beside the scan view, then the fixture card's own lines.
    const pair = within(sample).getByTestId("ob-pair");
    expect(pair).toHaveTextContent("The ad's photo");
    expect(pair).toHaveTextContent("Found in the building's 3D scan");
    expect(within(pair).getAllByTestId("sample-photo")).toHaveLength(2);
    expect(sample).toHaveTextContent("Taken in this building");
    expect(sample).toHaveTextContent("Zelle before a viewing. Red flag.Warning");
    await user.click(sample);
    // The photograph collapses to a strip and the thread takes the page.
    expect(screen.getByTestId("hero-street")).toHaveClass("hs-strip");
    expect(screen.getByTestId("ob-you")).toHaveTextContent("send the $600 deposit by Zelle");
    expect(screen.queryByTestId("ob-how")).not.toBeInTheDocument();
  });

  it("an empty send says what to do and starts nothing", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} />);
    await user.click(screen.getByRole("button", { name: SEND }));
    expect(screen.getByRole("button", { name: SEND })).toBeDisabled();
    await user.type(box(), "   {Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(/paste an ad, or add screenshots/i);
    expect(createCase).not.toHaveBeenCalled();
  });
});

describe("routing each message, shown honestly", () => {
  it("pasted ad text goes straight to the verdict, with no gate and no switch back to the Finder", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} />);
    await say(user, AD);

    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    expect(screen.queryByTestId("ob-switch")).not.toBeInTheDocument();
    await waitFor(() => expect(createCase).toHaveBeenCalledTimes(1));
    expect(createCase).toHaveBeenCalledWith(
      expect.objectContaining({ link: null, text: AD, files: [] }),
    );

    // No step in front of the result: nothing to approve first.
    const verdict = await screen.findByTestId("ob-verdict");
    expect(screen.queryByRole("button", { name: /i approve it/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /skip this/i })).not.toBeInTheDocument();
    expect(verdict).toHaveTextContent("Hold off for now");
    expect(verdict).toHaveTextContent("Code set this verdict");
    expect(within(verdict).getByTestId("source-chip")).toHaveTextContent("FIXTURE");
    expect(within(verdict).getByRole("link", { name: "Open the full report" })).toHaveAttribute(
      "href",
      "/case/7Q2M",
    );
    // Answer first: the red flag leads, the rest is one tap below.
    expect(within(verdict).getAllByRole("term")[0]).toHaveTextContent("Payment ask");
    await user.click(within(verdict).getByRole("button", { name: /how we know: all 5 checks/i }));
    expect(within(verdict).getAllByRole("term")).toHaveLength(5);
  });

  it("asking the poster for proof is offered after the verdict, as a second step", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" createCase={made()} checkingMs={0} />);
    await say(user, AD);
    const verdict = await screen.findByTestId("ob-verdict");
    // Closed until asked for; the draft is the one the API wrote; nothing is sent.
    expect(screen.queryByLabelText(/message to send/i)).not.toBeInTheDocument();
    await user.click(within(verdict).getByRole("button", { name: "Ask the poster for proof" }));
    expect(screen.getByLabelText(/message to send/i)).toHaveValue(
      "Send a photo of the door with today's date, please.",
    );
    expect(verdict).toHaveTextContent("Nothing is sent for you");
  });

  it("a red flag or a hold keeps three paths: the report, who to call, safer homes", async () => {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" createCase={made()} checkingMs={0} />);
    await say(user, AD);
    const verdict = await screen.findByTestId("ob-verdict");
    expect(within(verdict).getByRole("link", { name: "Open the full report" })).toBeInTheDocument();
    const next = within(verdict).getAllByRole("button", { hidden: false });
    const names = next.map((b) => b.textContent);
    expect(names).toContain("Who do I call?");
    expect(names).toContain("Find safer homes");
    for (const gone of ["Show me on the map", "Replay a real case"])
      expect(names).not.toContain(gone);
    expect(within(verdict).queryByText("Get ready to visit")).not.toBeInTheDocument();
    expect(within(verdict).queryByTestId("ob-walk")).not.toBeInTheDocument();
  });

  it("a clean result keeps every path", () => {
    const clean: Card = {
      ...(cardHold as Card),
      state: "verified",
      rows: (cardHold as Card).rows.map((r) => ({
        ...r,
        lines: r.lines.map((l) => ({ ...l, tone: "ok" as const })),
      })),
    };
    render(<VerdictView card={clean} source="fixture" onFollow={() => {}} />);
    const verdict = screen.getByTestId("ob-verdict");
    expect(within(verdict).getByRole("link", { name: "Get ready to visit" })).toBeInTheDocument();
    expect(within(verdict).getByTestId("ob-walk")).toHaveTextContent("Walk it first");
    for (const label of ["Find safer homes", "Show me on the map", "Replay a real case"])
      expect(within(verdict).getByRole("button", { name: label })).toBeInTheDocument();
    expect(within(verdict).queryByRole("button", { name: "Who do I call?" })).toBeNull();
  });

  it("a listing URL starts the check with the link", async () => {
    const user = userEvent.setup();
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} />);
    await say(user, "zillow.com/homedetails/123");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    await waitFor(() =>
      expect(createCase).toHaveBeenCalledWith(
        expect.objectContaining({ link: "https://zillow.com/homedetails/123", text: null }),
      ),
    );
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
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} />);
    await say(user, "2 bed under $2,000 with parking");
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Finding places");
    await user.click(screen.getByTestId("ob-switch"));
    expect(screen.getByTestId("ob-route")).toHaveTextContent("Checking this as an ad");
    await waitFor(() => expect(createCase).toHaveBeenCalledTimes(1));
  });

  it("screenshots alone start the check; a PDF is refused by name", async () => {
    const user = userEvent.setup({ applyAccept: false });
    const createCase = made();
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} />);
    const input = document.getElementById("photos") as HTMLInputElement;
    await user.upload(input, new File(["x"], "lease.pdf", { type: "application/pdf" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("lease.pdf is not a photo");
    await user.upload(input, new File(["x"], "ad.png", { type: "image/png" }));
    expect(screen.getByRole("list", { name: "Added screenshots" })).toHaveTextContent("ad.png");
    await user.click(screen.getByRole("button", { name: SEND }));
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
    render(<OneBox mode="fixture" createCase={createCase} checkingMs={0} />);
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

// With a case in the thread, a follow-up is about THAT case and is answered from its card, in the
// API's own words. The Finder is never asked.
describe("follow-ups answer about the case on screen", () => {
  const card = cardHold as Card;

  async function withCase() {
    const user = userEvent.setup();
    render(<OneBox mode="fixture" createCase={made()} checkingMs={0} />);
    await say(user, AD);
    await screen.findByTestId("ob-verdict");
    return user;
  }
  const reply = () => {
    const all = screen.getAllByTestId("ob-answer");
    return all[all.length - 1]!;
  };

  it("why: the summary and what does not check out, exactly as the card words them", async () => {
    const user = await withCase();
    await say(user, "why?");
    const a = reply();
    for (const line of [...card.summary!, ...card.does_not!]) expect(a).toHaveTextContent(line);
    expect(a).not.toHaveTextContent(/places|rent a month/i);
    expect(screen.queryByTestId("ob-places")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ob-switch")).not.toBeInTheDocument();
    expect(screen.queryByText("What's your max rent a month?")).not.toBeInTheDocument();
  });

  it("is it safe: the headline, what checks out and what does not", async () => {
    const user = await withCase();
    await say(user, "is it safe?");
    const a = reply();
    expect(a).toHaveTextContent("Hold off for now");
    for (const line of [...card.checks_out!, ...card.does_not!]) expect(a).toHaveTextContent(line);
    expect(a).toHaveTextContent("Not checkedID, lease, ownership");
  });

  it("what now: the card's own rules, and not to pay yet", async () => {
    const user = await withCase();
    await say(user, "what now?");
    const a = reply();
    expect(a).toHaveTextContent("Do not pay yet");
    for (const line of card.footer) expect(a).toHaveTextContent(line);
    expect(within(a).getByRole("link", { name: "Open the full report" })).toHaveAttribute(
      "href",
      "/case/7Q2M",
    );
  });

  it("who do I call: not the ad's number; the office on record and where to report", async () => {
    const user = await withCase();
    await user.click(screen.getByRole("button", { name: "Who do I call?" }));
    const a = reply();
    expect(a).toHaveTextContent("Not the number in the ad");
    expect(within(a).getByRole("link", { name: /Report it to the FTC/ })).toHaveAttribute(
      "href",
      "https://reportfraud.ftc.gov/",
    );
    expect(within(a).getByRole("link", { name: /IC3/ })).toHaveAttribute(
      "href",
      "https://www.ic3.gov/",
    );
    expect(screen.queryByTestId("ob-places")).not.toBeInTheDocument();
  });

  it("any other question about the case gets the summary and what can be asked", async () => {
    const user = await withCase();
    await say(user, "what about the rent?");
    const a = reply();
    expect(a).toHaveTextContent(card.summary![0]!);
    expect(a).toHaveTextContent(/ask why, who to call/i);
  });

  it("safer homes start from the ad's own rent and beds, without asking for a budget", async () => {
    const user = await withCase();
    await user.click(screen.getByRole("button", { name: "Find safer homes" }));
    const mine = screen.getAllByTestId("ob-you");
    expect(mine[mine.length - 1]).toHaveTextContent(
      "Find me safer places like this, 2 bed, under $1,350",
    );
    expect(await screen.findByTestId("ob-places")).toHaveTextContent("2+ bed, under $1,350");
    expect(screen.queryByText("What's your max rent a month?")).not.toBeInTheDocument();
  });
});

describe("the docked box leaves room under the thread", () => {
  it("sets --ob-dock-h to the box's measured height and keeps it current", async () => {
    let height = 132;
    let notify: () => void = () => {};
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          notify = cb;
        }
        observe() {}
        disconnect() {}
      },
    );
    const rect = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(() => ({ height }) as DOMRect);
    const user = userEvent.setup();
    render(<OneBox mode="fixture" createCase={made()} checkingMs={0} />);
    await say(user, AD);
    const host = screen.getByTestId("one-box");
    await waitFor(() => expect(host.style.getPropertyValue("--ob-dock-h")).toBe("132px"));
    height = 201.4;
    notify();
    expect(host.style.getPropertyValue("--ob-dock-h")).toBe("202px");
    // On a phone the box is pinned above the tab bar: that offset is covered room too.
    (document.querySelector(".ob-dock") as HTMLElement).style.bottom = "56px";
    notify();
    expect(host.style.getPropertyValue("--ob-dock-h")).toBe("258px");
    rect.mockRestore();
    vi.unstubAllGlobals();
  });
});
