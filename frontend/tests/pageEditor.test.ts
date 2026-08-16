// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/client";
import type { PageDto, PanelDto } from "../src/api/types";
import { renderToolbar } from "../src/shell/toolbar";
import { renderPageEditor } from "../src/views/pageEditor";
import { mountTestRoot, resetTestRoot } from "./domHarness";

/**
 * Boundary (02-VALIDATION.md's Manual-Only Verifications): rendering
 * fidelity and real-browser zoom persistence stay named manual checks.
 * This file asserts structure, copy and call sequencing only -- never a
 * drawn pixel or an actual coordinate transform.
 */

vi.mock("../src/api/client", () => {
  class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }
  return {
    ApiError,
    api: {
      pages: {
        get: vi.fn(),
        imageUrl: vi.fn(() => "/api/pages/1/image"),
        confirmStage: vi.fn(),
      },
      panels: {
        list: vi.fn(),
        create: vi.fn(),
        moveVertex: vi.fn(),
        setPolygon: vi.fn(),
        remove: vi.fn(),
      },
      protected: {
        list: vi.fn(),
        create: vi.fn(),
        moveVertex: vi.fn(),
        setPolygon: vi.fn(),
        remove: vi.fn(),
      },
    },
  };
});

const CTX_METHODS = [
  "clearRect",
  "save",
  "restore",
  "beginPath",
  "moveTo",
  "lineTo",
  "closePath",
  "stroke",
  "fill",
  "arc",
  "setLineDash",
  "drawImage",
  "fillText",
] as const;

function buildContextStub(): Record<string, unknown> {
  const stub: Record<string, unknown> = {};
  for (const method of CTX_METHODS) stub[method] = vi.fn();
  stub.createPattern = vi.fn(() => null);
  return stub;
}

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    x: left,
    y: top,
    toJSON() {
      return this;
    },
  } as DOMRect;
}

/**
 * A `src` setter that resolves `onload` synchronously -- avoids a real
 * image load and keeps `renderPageEditor`'s boot chain deterministic
 * without timers, mirroring canvasEditor.test.ts's synchronous
 * `requestAnimationFrame` stub for the same reason.
 */
class ImmediateImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private _src = "";
  set src(value: string) {
    this._src = value;
    this.onload?.();
  }
  get src(): string {
    return this._src;
  }
}

function defaultPage(overrides: Partial<PageDto> = {}): PageDto {
  return {
    id: 1,
    volume_id: 10,
    index: 0,
    original_name: "Page 1",
    width: 1000,
    height: 1000,
    stage: "panels",
    image_url: "/api/pages/1/image",
    ...overrides,
  };
}

const onePanel: PanelDto = {
  id: 1,
  page_id: 1,
  x: 0,
  y: 0,
  width: 100,
  height: 100,
  reading_order: 1,
  polygon: [
    [0, 0],
    [100, 0],
    [100, 100],
    [0, 100],
  ],
};

function setup(pageOverrides: Partial<PageDto> = {}): { appRoot: HTMLElement; viewMount: HTMLElement; teardown: () => void } {
  const appRoot = mountTestRoot();
  const toolbarMount = document.createElement("div");
  appRoot.append(toolbarMount);
  renderToolbar(toolbarMount);

  const viewMount = document.createElement("div");
  appRoot.append(viewMount);

  vi.mocked(api.pages.get).mockResolvedValue(defaultPage(pageOverrides));

  const teardown = renderPageEditor(viewMount, { pageId: 1 });
  return { appRoot, viewMount, teardown };
}

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    buildContextStub() as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue(rect(0, 0, 1000, 1000));
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback): number => {
    cb(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  vi.stubGlobal("Image", ImmediateImage);

  vi.mocked(api.panels.list).mockResolvedValue({ panels: [] });
  vi.mocked(api.protected.list).mockResolvedValue({ masks: [], detection_failed: false, detection_message: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  resetTestRoot();
});

describe("Panels gate", () => {
  it("renders the CTA disabled with the empty-state tooltip when the page has zero panels", async () => {
    const { appRoot, viewMount } = setup({ stage: "panels" });

    await vi.waitFor(() => {
      const button = appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm");
      expect(button?.textContent).toBe("Confirm & Continue to Protected");
      expect(button?.disabled).toBe(true);
      expect(button?.title).toBe("Draw at least one panel before continuing.");
    });
  });

  it("enables the CTA once the page has one panel", async () => {
    vi.mocked(api.panels.list).mockResolvedValue({ panels: [onePanel] });
    const { appRoot, viewMount } = setup({ stage: "panels" });

    await vi.waitFor(() => {
      const button = appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm");
      expect(button?.disabled).toBe(false);
    });
  });
});

describe("Protected gate", () => {
  it("is never disabled by mask count", async () => {
    const { appRoot, viewMount } = setup({ stage: "protected" });

    await vi.waitFor(() => {
      const button = appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm");
      expect(button?.textContent).toBe("Confirm & Continue to Zones");
      expect(button?.disabled).toBe(false);
    });
  });

  it("renders the persistent SFX helper text while Protected tool mode is active", async () => {
    const { appRoot, viewMount } = setup({ stage: "protected" });

    await vi.waitFor(() => {
      const helper = viewMount.querySelector<HTMLElement>(".page-editor-helper-text");
      expect(helper?.hidden).toBe(false);
      expect(helper?.textContent).toBe(
        "Bubbles are proposed automatically. Sound effects aren't yet — check for any and draw them by hand.",
      );
    });
  });
});

describe("Confirming Panels", () => {
  it("shows the detection-failure banner and renders no dialog element when detection_failed is true", async () => {
    vi.mocked(api.panels.list).mockResolvedValue({ panels: [onePanel] });
    vi.mocked(api.pages.confirmStage).mockResolvedValue({
      page: defaultPage({ stage: "protected" }),
      detection_failed: false,
      detection_message: null,
    });
    vi.mocked(api.protected.list).mockResolvedValueOnce({
      masks: [],
      detection_failed: false,
      detection_message: null,
    });
    vi.mocked(api.protected.list).mockResolvedValueOnce({
      masks: [],
      detection_failed: true,
      detection_message: "no bubbles found",
    });

    const { appRoot, viewMount } = setup({ stage: "panels" });

    await vi.waitFor(() => {
      expect(appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm")?.disabled).toBe(false);
    });
    appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm")!.click();

    await vi.waitFor(() => {
      const banner = viewMount.querySelector<HTMLElement>(".page-editor-banner");
      expect(banner?.hidden).toBe(false);
      expect(banner?.textContent).toBe("Bubble detection failed — you can still draw protected masks by hand.");
    });
    expect(viewMount.querySelector("dialog")).toBeNull();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
  });

  it("calls confirmStage exactly once, then protected.list, and never navigates", async () => {
    vi.mocked(api.panels.list).mockResolvedValue({ panels: [onePanel] });
    vi.mocked(api.pages.confirmStage).mockResolvedValue({
      page: defaultPage({ stage: "protected" }),
      detection_failed: false,
      detection_message: null,
    });

    const { appRoot, viewMount } = setup({ stage: "panels" });
    await vi.waitFor(() => {
      expect(appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm")?.disabled).toBe(false);
    });

    const hashBefore = location.hash;
    appRoot.querySelector<HTMLButtonElement>(".page-editor-confirm")!.click();

    await vi.waitFor(() => {
      expect(api.pages.confirmStage).toHaveBeenCalledTimes(1);
      expect(api.protected.list).toHaveBeenCalled();
    });
    expect(location.hash).toBe(hashBefore);
  });
});

describe("Undo control", () => {
  it("carries aria-label 'Undo last edit' and starts muted", async () => {
    const { appRoot, viewMount } = setup({ stage: "panels" });

    await vi.waitFor(() => {
      const undo = appRoot.querySelector<HTMLButtonElement>('[aria-label="Undo last edit"]');
      expect(undo).not.toBeNull();
      expect(undo!.disabled).toBe(true);
    });
  });
});

describe("Teardown", () => {
  it("removes the view's DOM and its toolbar contribution", async () => {
    const { viewMount, teardown } = setup({ stage: "panels" });

    await vi.waitFor(() => {
      expect(viewMount.querySelector(".page-editor")).not.toBeNull();
    });
    const toolbarSlot = document.querySelector(".app-toolbar-slot");
    expect(toolbarSlot?.childElementCount).toBeGreaterThan(0);

    teardown();

    expect(viewMount.querySelector(".page-editor")).toBeNull();
    expect(toolbarSlot?.childElementCount).toBe(0);
  });
});
