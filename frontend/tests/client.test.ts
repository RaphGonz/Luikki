import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, apiUrl } from "../src/api/client";
import type { PanelListDto, ProtectedMaskDto } from "../src/api/types";

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

/**
 * One URL/method/body assertion per Phase 2 client method (13 total,
 * 02-12-PLAN.md Task 1) -- these are the only thing standing between a
 * renamed route and a silent 404 at runtime.
 */
function stubFetch(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async () =>
      new Response(body === undefined ? null : JSON.stringify(body), { status }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>): [string, RequestInit | undefined] {
  const call = fetchMock.mock.calls.at(-1) as [string, RequestInit | undefined];
  return call;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api.panels", () => {
  const panelList: PanelListDto = { panels: [] };

  it("list issues GET /api/pages/{pageId}/panels", async () => {
    const fetchMock = stubFetch(200, panelList);
    await api.panels.list(3);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/panels");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("create issues POST /api/pages/{pageId}/panels with the polygon body", async () => {
    const fetchMock = stubFetch(201, panelList);
    await api.panels.create(3, [
      [0, 0],
      [10, 0],
      [10, 10],
    ]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/panels");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      polygon: [
        [0, 0],
        [10, 0],
        [10, 10],
      ],
    });
  });

  it("moveVertex issues PATCH /api/panels/{panelId}/vertex/{index}", async () => {
    const fetchMock = stubFetch(200, panelList);
    await api.panels.moveVertex(5, 2, [7, 8]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/panels/5/vertex/2");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({ x: 7, y: 8 });
  });

  it("setPolygon issues PATCH /api/panels/{panelId}/polygon", async () => {
    const fetchMock = stubFetch(200, panelList);
    await api.panels.setPolygon(5, [
      [0, 0],
      [1, 0],
      [1, 1],
    ]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/panels/5/polygon");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({
      polygon: [
        [0, 0],
        [1, 0],
        [1, 1],
      ],
    });
  });

  it("remove issues DELETE /api/panels/{panelId} and resolves to the renumbered list", async () => {
    const fetchMock = stubFetch(200, panelList);
    const result = await api.panels.remove(5);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/panels/5");
    expect(init?.method).toBe("DELETE");
    expect(result).toEqual(panelList);
  });
});

describe("api.protected", () => {
  const mask: ProtectedMaskDto = {
    id: 1,
    page_id: 3,
    kind: "bubble",
    polygon: [
      [0, 0],
      [1, 0],
      [1, 1],
    ],
    touched: true,
    area: 1,
    bbox: [0, 0, 1, 1],
  };
  const maskList = { masks: [mask], detection_failed: false, detection_message: null };

  it("list issues GET /api/pages/{pageId}/protected", async () => {
    const fetchMock = stubFetch(200, maskList);
    await api.protected.list(3);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/protected");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("create issues POST /api/pages/{pageId}/protected with kind and polygon", async () => {
    const fetchMock = stubFetch(201, mask);
    await api.protected.create(3, "bubble", [
      [0, 0],
      [1, 0],
      [1, 1],
    ]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/protected");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      kind: "bubble",
      polygon: [
        [0, 0],
        [1, 0],
        [1, 1],
      ],
    });
  });

  it("moveVertex issues PATCH /api/protected/{maskId}/vertex/{index}", async () => {
    const fetchMock = stubFetch(200, mask);
    await api.protected.moveVertex(9, 1, [4, 5]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/protected/9/vertex/1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({ x: 4, y: 5 });
  });

  it("setPolygon issues PATCH /api/protected/{maskId}/polygon", async () => {
    const fetchMock = stubFetch(200, mask);
    await api.protected.setPolygon(9, [
      [0, 0],
      [2, 0],
      [2, 2],
    ]);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/protected/9/polygon");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({
      polygon: [
        [0, 0],
        [2, 0],
        [2, 2],
      ],
    });
  });

  it("remove issues DELETE /api/protected/{maskId} and resolves to void (204)", async () => {
    const fetchMock = stubFetch(204, undefined);
    const result = await api.protected.remove(9);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/protected/9");
    expect(init?.method).toBe("DELETE");
    expect(result).toBeUndefined();
  });
});

describe("api.pages stage gates", () => {
  const page = {
    id: 3,
    volume_id: 1,
    index: 0,
    original_name: "p1.png",
    width: 100,
    height: 100,
    stage: "protected" as const,
    image_url: "/api/pages/3/image",
  };
  const stageConfirm = { page, detection_failed: false, detection_message: null };
  const goBackTargets = [
    {
      stage: "panels" as const,
      display_name: "Panels",
      heading: "Go back to Panels?",
      body: "This discards 4 protected masks and re-runs bubble detection for the whole page.",
      confirm_label: "Go back and discard 4 edits",
      cancel_label: "Stay on Protected",
      discarded_count: 4,
    },
  ];

  it("confirmStage issues POST /api/pages/{pageId}/stage/confirm", async () => {
    const fetchMock = stubFetch(200, stageConfirm);
    const result = await api.pages.confirmStage(3);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/stage/confirm");
    expect(init?.method).toBe("POST");
    expect(result).toEqual(stageConfirm);
  });

  it("goBackTargets issues GET /api/pages/{pageId}/stage/go-back-targets", async () => {
    const fetchMock = stubFetch(200, goBackTargets);
    const result = await api.pages.goBackTargets(3);
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/stage/go-back-targets");
    expect(init?.method ?? "GET").toBe("GET");
    expect(result).toEqual(goBackTargets);
  });

  it("goBack issues POST /api/pages/{pageId}/stage/go-back with the target body", async () => {
    const fetchMock = stubFetch(200, stageConfirm);
    await api.pages.goBack(3, "panels");
    const [url, init] = lastCall(fetchMock);
    expect(url).toBe("/api/pages/3/stage/go-back");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ target: "panels" });
  });
});
