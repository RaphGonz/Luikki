import { describe, expect, it } from "vitest";

import { ApiError, apiUrl } from "../src/api/client";

describe("apiUrl", () => {
  it("always starts with /api/", () => {
    expect(apiUrl("/projects").startsWith("/api/")).toBe(true);
    expect(apiUrl("projects").startsWith("/api/")).toBe(true);
  });

  it("builds the expected path", () => {
    expect(apiUrl("/pages/123")).toBe("/api/pages/123");
    expect(apiUrl("/projects/recent")).toBe("/api/projects/recent");
  });

  it("encodes query parameter values", () => {
    const url = apiUrl("/pages/", { volume_id: 7, note: "a b" });
    expect(url).toBe("/api/pages/?volume_id=7&note=a+b");
  });

  it("omits undefined query values", () => {
    const url = apiUrl("/pages/", { volume_id: 7, cursor: undefined });
    expect(url).toBe("/api/pages/?volume_id=7");
  });

  it("returns the bare path when there are no query params", () => {
    expect(apiUrl("/projects/current")).toBe("/api/projects/current");
  });
});

describe("ApiError.fromResponse", () => {
  it("extracts a plain detail string", async () => {
    const res = new Response(
      JSON.stringify({ detail: "That folder isn't a ComicColor project." }),
      { status: 400 },
    );
    const err = await ApiError.fromResponse(res);
    expect(err.status).toBe(400);
    expect(err.detail).toBe("That folder isn't a ComicColor project.");
  });

  it("flattens a 422 validation-error array into a readable sentence", async () => {
    const res = new Response(
      JSON.stringify({
        detail: [{ loc: ["body", "name"], msg: "field required", type: "missing" }],
      }),
      { status: 422 },
    );
    const err = await ApiError.fromResponse(res);
    expect(err.status).toBe(422);
    expect(err.detail).toContain("name");
    expect(err.detail).toContain("field required");
  });

  it("falls back to a status-derived sentence when the body isn't JSON", async () => {
    const res = new Response("not json at all", { status: 500 });
    const err = await ApiError.fromResponse(res);
    expect(err.status).toBe(500);
    expect(err.detail.length).toBeGreaterThan(0);
  });

  it("never produces the string 'Something went wrong'", async () => {
    const plainBody = new Response("not json at all", { status: 500 });
    const errFromPlainBody = await ApiError.fromResponse(plainBody);

    const detailBody = new Response(JSON.stringify({ detail: "Upload failed." }), {
      status: 400,
    });
    const errFromDetailBody = await ApiError.fromResponse(detailBody);

    // The only appearance of this phrase anywhere in this suite is right
    // here, in the assertion that forbids the client from ever producing it.
    expect(errFromPlainBody.detail.toLowerCase()).not.toContain("something went wrong");
    expect(errFromDetailBody.detail.toLowerCase()).not.toContain("something went wrong");
  });
});
