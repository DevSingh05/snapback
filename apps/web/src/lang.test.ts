import { afterEach, describe, expect, it, vi } from "vitest";

import { LANG_KEY, loadLang, saveLang } from "./lang";

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("the report language", () => {
  it("is English by default and never reads the browser's language", () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("es-MX");
    expect(loadLang("")).toBe("en");
  });

  it("?lang=es opens in Spanish and beats the saved choice", () => {
    saveLang("en");
    expect(loadLang("?lang=es")).toBe("es");
    saveLang("es");
    expect(loadLang("?lang=en")).toBe("en");
  });

  it("remembers the last choice per browser", () => {
    saveLang("es");
    expect(window.localStorage.getItem(LANG_KEY)).toBe("es");
    expect(loadLang("")).toBe("es");
  });

  it("ignores a value it does not know", () => {
    window.localStorage.setItem(LANG_KEY, "fr");
    expect(loadLang("?lang=fr")).toBe("en");
  });

  it("works with storage blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => saveLang("es")).not.toThrow();
    expect(loadLang("")).toBe("en");
  });
});
