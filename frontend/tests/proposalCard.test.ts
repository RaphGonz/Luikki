import { describe, expect, it } from "vitest";

import {
  acceptPayload,
  entryLabel,
  ProposalValidationError,
  type ProposalSelection,
} from "../src/components/proposalCard";

describe("entryLabel", () => {
  it("joins character and part with ' / '", () => {
    expect(entryLabel("Kaito", "hair")).toBe("Kaito / hair");
  });

  it("trims surrounding whitespace on both sides", () => {
    expect(entryLabel("  Kaito  ", "  hair  ")).toBe("Kaito / hair");
  });
});

describe("acceptPayload", () => {
  const baseSelection: ProposalSelection = {
    characterName: "Kaito",
    entries: [
      { index: 0, selected: true, part: "hair" },
      { index: 1, selected: false, part: "" },
      { index: 2, selected: true, part: "eyes" },
    ],
  };

  it("includes only the selected proposal indices", () => {
    const result = acceptPayload(baseSelection);
    expect(result.items.map((i) => i.index)).toEqual([0, 2]);
  });

  it("preserves each selected entry's part", () => {
    const result = acceptPayload(baseSelection);
    expect(result.items).toEqual([
      { index: 0, part: "hair" },
      { index: 2, part: "eyes" },
    ]);
  });

  it("trims the character name and every part", () => {
    const result = acceptPayload({
      characterName: "  Kaito  ",
      entries: [{ index: 0, selected: true, part: "  hair  " }],
    });
    expect(result.character_name).toBe("Kaito");
    expect(result.items[0]).toEqual({ index: 0, part: "hair" });
  });

  it("throws a ProposalValidationError on an empty character name", () => {
    expect(() =>
      acceptPayload({
        characterName: "   ",
        entries: [{ index: 0, selected: true, part: "hair" }],
      }),
    ).toThrow(ProposalValidationError);
  });

  it("throws a ProposalValidationError when a selected entry has no part", () => {
    expect(() =>
      acceptPayload({
        characterName: "Kaito",
        entries: [{ index: 0, selected: true, part: "   " }],
      }),
    ).toThrow(ProposalValidationError);
  });

  it("does not require a part on an unselected entry", () => {
    expect(() =>
      acceptPayload({
        characterName: "Kaito",
        entries: [{ index: 0, selected: false, part: "" }],
      }),
    ).not.toThrow();
  });

  it("returns an object whose shape matches SheetAcceptRequest exactly", () => {
    const result = acceptPayload(baseSelection);
    expect(Object.keys(result).sort()).toEqual(["character_name", "items"]);
    for (const item of result.items) {
      expect(Object.keys(item).sort()).toEqual(["index", "part"]);
    }
  });
});
