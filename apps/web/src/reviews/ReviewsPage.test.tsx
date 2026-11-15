import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { matchRoute } from "../App";
import data from "./reviews.json";
import { ReviewsPage } from "./ReviewsPage";
import { firstNameOnly, publicQuotes, summarize, type ReviewResponse } from "./summary";

const r = (o: Partial<ReviewResponse> = {}): ReviewResponse => ({
  q1_easy: 4,
  q2_would_pay: "no",
  q3_trust: 4,
  q4_use_again: "yes",
  ...o,
});

const THREE: ReviewResponse[] = [
  r({
    q1_easy: 5,
    q3_trust: 4,
    q2_would_pay: "no",
    q4_use_again: "yes",
    q6_quote: "Clear.",
    q6_name: "Sam Q",
  }),
  r({ q1_easy: 4, q3_trust: 3, q2_would_pay: "not sure", q4_use_again: "maybe" }),
  r({
    q1_easy: 3,
    q3_trust: 5,
    q2_would_pay: "yes",
    q4_use_again: "no",
    q6_quote: "  ",
    q6_name: "Lee",
  }),
];

describe("summary maths", () => {
  it("averages to one decimal and rounds percentages, all over n", () => {
    const s = summarize(THREE);
    expect(s).toEqual({ n: 3, avgEasy: 4, avgTrust: 4, useAgainPct: 33, wouldNotPayPct: 33 });
    expect(summarize([r({ q1_easy: 4 }), r({ q1_easy: 5 })]).avgEasy).toBe(4.5);
  });
  it("is null, not NaN, with no responses", () => {
    expect(summarize([])).toEqual({
      n: 0,
      avgEasy: null,
      avgTrust: null,
      useAgainPct: null,
      wouldNotPayPct: null,
    });
  });
});

describe("quotes", () => {
  it("keeps only rows with a real quote and shows first name only", () => {
    expect(publicQuotes(THREE)).toEqual([{ quote: "Clear.", by: "Sam" }]);
    expect(firstNameOnly(undefined)).toBe("Anonymous");
    expect(firstNameOnly("J.K.")).toBe("J.K.");
  });
});

describe("the page", () => {
  it("shipped file is empty with no form link", () => {
    expect(data.responses).toEqual([]);
    expect(data.form_url).toBe("");
  });
  it("empty state shows the realtor quote, the hallway line and the rate link", () => {
    render(<ReviewsPage file={{ updated: "", form_url: "", responses: [] }} />);
    expect(screen.getByTestId("realtor-quote")).toHaveTextContent("Ashwin Veeravalli");
    expect(screen.getByTestId("realtor-quote")).not.toHaveTextContent(/main focus/);
    expect(
      screen.getByText("Hallway test results are added here, with n, as they come in"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/go up before judging/)).toBeNull();
    expect(screen.getByRole("link", { name: "Rate SNAPBACK (2 minutes)" })).toHaveAttribute(
      "href",
      "https://forms.gle/rDczNc1TT1EAJcw6A",
    );
    expect(screen.queryByText(/out of 5/)).toBeNull();
  });
  it("shows summary with n on every number, only shared quotes, and the transparency line", () => {
    render(<ReviewsPage file={{ updated: "", form_url: "", responses: THREE }} />);
    expect(screen.getByRole("heading", { name: "3 reviews" })).toBeInTheDocument();
    expect(screen.getAllByText("n = 3")).toHaveLength(4);
    const quotes = screen.getByRole("heading", { name: "In their words" }).closest("section")!;
    expect(within(quotes).getAllByRole("listitem")).toHaveLength(1);
    expect(within(quotes).getByText("Sam")).toBeInTheDocument();
    expect(screen.queryByText("Lee")).toBeNull();
    expect(screen.queryByText("Sam Q")).toBeNull();
    expect(screen.queryByRole("link", { name: "Leave a review" })).toBeNull();
    expect(
      screen.getByText(/Every response is counted here, good or bad\. Quotes appear only when/),
    ).toBeInTheDocument();
  });
  it("routes /reviews", () => {
    expect(matchRoute("/reviews")).toEqual({ name: "reviews" });
    expect(matchRoute("/reviews/")).toEqual({ name: "reviews" });
  });
});
