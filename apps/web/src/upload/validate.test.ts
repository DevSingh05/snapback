import { describe, expect, it } from "vitest";

import {
  MAX_FILES,
  MAX_FILE_BYTES,
  addFiles,
  classifyListingText,
  validateLink,
  validateSubmission,
} from "./validate";

function file(name: string, type: string, size = 1000): File {
  const f = new File(["x"], name, { type });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("validateLink", () => {
  it("accepts an https listing link and trims spaces", () => {
    expect(validateLink("  https://www.zillow.com/homedetails/123  ")).toEqual({
      ok: true,
      url: "https://www.zillow.com/homedetails/123",
    });
  });

  it("adds https:// when the renter pastes a bare domain", () => {
    const r = validateLink("craigslist.org/apa/d/nice-flat/1.html");
    expect(r).toEqual({ ok: true, url: "https://craigslist.org/apa/d/nice-flat/1.html" });
  });

  it.each(["javascript:alert(1)", "ftp://x.com/a", "file:///etc/passwd"])(
    "rejects the non-web scheme %s",
    (raw) => {
      expect(validateLink(raw).ok).toBe(false);
    },
  );

  it("rejects text with spaces or no dot and says how to fix it", () => {
    for (const raw of ["not a link", "localhost", "http://nodot"]) {
      const r = validateLink(raw);
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.error).toMatch(/Paste the full address/);
    }
  });
});

describe("validateLink strictness", () => {
  it("rejects an email address and says it is not a listing link", () => {
    for (const raw of ["john@gmail.com", "https://john@gmail.com", "https://u:p@zillow.com/x"]) {
      const r = validateLink(raw);
      expect(r.ok).toBe(false);
      if (!r.ok) expect(r.error).toMatch(/email address/);
    }
  });

  it("does not treat 1.5BR or an unknown suffix as a bare link", () => {
    expect(validateLink("1.5BR").ok).toBe(false);
    expect(validateLink("foo.zzzz/x").ok).toBe(false);
    expect(classifyListingText("1.5BR").kind).toBe("text");
    expect(classifyListingText("$1.800/mo").kind).toBe("text");
  });

  it("still accepts an explicit https link on an unusual suffix", () => {
    expect(validateLink("https://rooms.example.xyz/1").ok).toBe(true);
  });
});

describe("classifyListingText", () => {
  it("tells links from pasted listing text from nothing", () => {
    expect(classifyListingText("https://a.com/x").kind).toBe("link");
    expect(classifyListingText("2BR near campus, $1800, no fee, text me to see it").kind).toBe(
      "text",
    );
    expect(classifyListingText("   ").kind).toBe("empty");
  });
});

describe("addFiles", () => {
  it("accepts jpeg, png, webp and heic", () => {
    const r = addFiles(
      [],
      [
        file("a.jpg", "image/jpeg"),
        file("b.png", "image/png"),
        file("c.webp", "image/webp"),
        file("d.heic", "image/heic"),
      ],
    );
    expect(r.files).toHaveLength(4);
    expect(r.errors).toEqual([]);
  });

  it("accepts a heic file whose type is blank by extension", () => {
    expect(addFiles([], [file("IMG_1.HEIC", "")]).files).toHaveLength(1);
  });

  it("rejects a PDF and names the file and the fix", () => {
    const r = addFiles([], [file("lease.pdf", "application/pdf")]);
    expect(r.files).toHaveLength(0);
    expect(r.errors[0]).toMatch(/lease\.pdf/);
    expect(r.errors[0]).toMatch(/screenshot/i);
  });

  it("rejects a file over the size limit but keeps the good ones", () => {
    const r = addFiles(
      [],
      [file("big.jpg", "image/jpeg", MAX_FILE_BYTES + 1), file("ok.jpg", "image/jpeg")],
    );
    expect(r.files.map((f) => f.name)).toEqual(["ok.jpg"]);
    expect(r.errors[0]).toMatch(/big\.jpg.*10 MB/);
  });

  it("caps the total count and skips duplicates", () => {
    const existing = Array.from({ length: MAX_FILES - 1 }, (_, i) =>
      file(`p${i}.jpg`, "image/jpeg"),
    );
    const r = addFiles(existing, [
      file("p0.jpg", "image/jpeg"),
      file("n1.jpg", "image/jpeg"),
      file("n2.jpg", "image/jpeg"),
    ]);
    expect(r.files).toHaveLength(MAX_FILES);
    expect(r.errors.join(" ")).toMatch(new RegExp(`${MAX_FILES} photos`));
  });
});

describe("validateSubmission", () => {
  it("needs a link, listing text or at least one photo", () => {
    const r = validateSubmission({ text: "", files: [] });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toMatch(/Paste a listing link or add screenshots/);
  });

  it("passes with only screenshots", () => {
    expect(validateSubmission({ text: "", files: [file("a.png", "image/png")] }).ok).toBe(true);
  });

  it("fails a link-looking text that is not a valid link", () => {
    expect(validateSubmission({ text: "https://", files: [] }).ok).toBe(false);
  });

  it("returns the link as a normalised url", () => {
    expect(validateSubmission({ text: "zillow.com/x/1", files: [] })).toMatchObject({
      ok: true,
      link: "https://zillow.com/x/1",
    });
  });
});
