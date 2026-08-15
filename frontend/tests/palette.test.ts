import { describe, expect, it } from "vitest";

import { toastCopy } from "../src/views/palette";

describe("toastCopy", () => {
  it("uses the singular form at exactly 1 page", () => {
    expect(toastCopy(1)).toBe("Updated on 1 page.");
  });

  it("uses the exact Copywriting Contract wording for a plural count", () => {
    expect(toastCopy(4)).toBe("Updated on 4 pages.");
  });

  it("uses the plural form at zero without reading as an error", () => {
    const copy = toastCopy(0);
    expect(copy).toBe("Updated on 0 pages.");
    expect(copy.toLowerCase()).not.toContain("error");
    expect(copy.toLowerCase()).not.toContain("fail");
  });

  it("never adds an exclamation mark or generic phrasing", () => {
    for (const n of [0, 1, 2, 4, 100]) {
      const copy = toastCopy(n);
      expect(copy).not.toContain("!");
      expect(copy.toLowerCase()).not.toContain("something went wrong");
    }
  });

  it("pluralises every count above 1", () => {
    expect(toastCopy(2)).toBe("Updated on 2 pages.");
    expect(toastCopy(100)).toBe("Updated on 100 pages.");
  });
});
