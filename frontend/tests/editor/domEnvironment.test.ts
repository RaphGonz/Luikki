// @vitest-environment jsdom
import { describe, it, expect, afterEach } from "vitest";
import { mountTestRoot, resetTestRoot } from "../domHarness";

/**
 * Proves the per-file jsdom opt-in path works (WR-14 / D-26). Every other
 * test file in this project keeps running under `environment: "node"`
 * (vitest.config.ts default) — this is the one exception, declared by its
 * own docblock, not by a global config change.
 */

afterEach(() => {
  resetTestRoot();
});

describe("jsdom environment path", () => {
  it("provides a real document", () => {
    expect(typeof document).not.toBe("undefined");
  });

  it("mountTestRoot returns an element attached to document.body", () => {
    const root = mountTestRoot();
    expect(root.parentElement).toBe(document.body);
    expect(document.body.contains(root)).toBe(true);
  });

  it("constructs a canvas element with a getContext function, even though the 2D context is not implemented (Pitfall 3's exact boundary)", () => {
    const canvas = document.createElement("canvas");
    expect(typeof canvas.getContext).toBe("function");
  });
});
