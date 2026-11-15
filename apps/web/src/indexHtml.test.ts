import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// index.html keeps a skipped page-to-page view transition out of the console. It must swallow
// exactly that error and nothing else.
const html = readFileSync(path.resolve(import.meta.dirname, "../index.html"), "utf8");
const code = /<script>([\s\S]*?)<\/script>/.exec(html)![1]!;
new Function(code)();

const prevented = (e: Event) => {
  window.dispatchEvent(e);
  return e.defaultPrevented;
};
const error = (message: string) => new ErrorEvent("error", { message, cancelable: true });
const rejection = (reason: unknown) => {
  const e = new Event("unhandledrejection", { cancelable: true });
  Object.assign(e, { reason });
  return e;
};

describe("the skipped view transition guard", () => {
  it("swallows the skipped-transition error", () => {
    expect(prevented(error("Uncaught InvalidStateError: Transition was skipped"))).toBe(true);
    expect(
      prevented(
        rejection(
          Object.assign(new Error("Transition was aborted because of invalid state."), {
            name: "InvalidStateError",
          }),
        ),
      ),
    ).toBe(true);
  });
  it("leaves every other error alone, even one that mentions a transition", () => {
    expect(prevented(error("Cannot read properties of undefined"))).toBe(false);
    expect(prevented(error("My transition failed: Transition was skipped by us"))).toBe(false);
    expect(prevented(rejection(new Error("Transition was skipped")))).toBe(false);
  });
});
