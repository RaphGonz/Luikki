import { describe, expect, it } from "vitest";

import { buildHash, parseRoute } from "../src/shell/router";

describe("parseRoute", () => {
  it("parses the picker route", () => {
    expect(parseRoute("#/picker")).toEqual({ kind: "picker" });
  });

  it("parses a volume route", () => {
    expect(parseRoute("#/volume/12")).toEqual({ kind: "volume", volumeId: 12 });
  });

  it("parses a page route", () => {
    expect(parseRoute("#/page/7")).toEqual({ kind: "page", pageId: 7 });
  });

  it("parses the page-editor route", () => {
    expect(parseRoute("#/page/7/edit")).toEqual({ kind: "pageEditor", pageId: 7 });
  });

  it("falls back to the picker route on a bad-id page-editor hash", () => {
    expect(parseRoute("#/page/abc/edit")).toEqual({ kind: "picker" });
  });

  it("parses the palette route", () => {
    expect(parseRoute("#/palette")).toEqual({ kind: "palette" });
  });

  it("falls back to the picker route on an empty hash", () => {
    expect(parseRoute("")).toEqual({ kind: "picker" });
    expect(parseRoute("#")).toEqual({ kind: "picker" });
  });

  it("falls back to the picker route on an unknown hash", () => {
    expect(parseRoute("#/nonsense")).toEqual({ kind: "picker" });
  });

  it("falls back to the picker route on a non-numeric id", () => {
    expect(parseRoute("#/volume/abc")).toEqual({ kind: "picker" });
    expect(parseRoute("#/page/12.5")).toEqual({ kind: "picker" });
  });

  it("falls back to the picker route on a negative id", () => {
    expect(parseRoute("#/volume/-1")).toEqual({ kind: "picker" });
  });
});

describe("buildHash <-> parseRoute round trip", () => {
  const validHashes = ["#/picker", "#/volume/12", "#/page/7", "#/page/7/edit", "#/palette"];

  it.each(validHashes)("round-trips %s", (hash) => {
    expect(buildHash(parseRoute(hash))).toBe(hash);
  });
});
