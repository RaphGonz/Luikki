// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GoBackTargetDto } from "../src/api/types";
import { openGoBackDialog } from "../src/components/goBackDialog";
import { mountTestRoot, resetTestRoot } from "./domHarness";

/**
 * 01-UI-SPEC.md §3 / 02-UI-SPEC.md §8: this dialog renders only
 * server-computed strings. Every assertion below checks literal DTO field
 * values reaching `textContent` -- never a client-assembled sentence.
 */

const protectedTarget: GoBackTargetDto = {
  stage: "panels",
  display_name: "Panels",
  heading: "Go back to Panels?",
  body: "This discards 4 protected masks and re-runs bubble detection for the whole page.",
  confirm_label: "Go back and discard 4 edits",
  cancel_label: "Stay on Protected",
  discarded_count: 4,
};

const importTarget: GoBackTargetDto = {
  stage: "import",
  display_name: "Import",
  heading: "Go back to Import?",
  body: "This discards 6 panel polygons and 4 protected masks, and re-runs panel detection for the whole page.",
  confirm_label: "Go back and discard 10 edits",
  cancel_label: "Stay on Panels",
  discarded_count: 10,
};

let mount: HTMLElement;

beforeEach(() => {
  mount = mountTestRoot();
});

afterEach(() => {
  resetTestRoot();
  vi.restoreAllMocks();
});

describe("openGoBackDialog -- zero targets", () => {
  it("renders nothing and returns a no-op teardown", () => {
    const onConfirm = vi.fn();
    const dismiss = openGoBackDialog(mount, [], onConfirm);

    expect(mount.children.length).toBe(0);
    expect(() => dismiss()).not.toThrow();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("openGoBackDialog -- one target", () => {
  it("renders heading, body, confirm and cancel labels as exact textContent", () => {
    openGoBackDialog(mount, [protectedTarget], vi.fn());

    expect(mount.querySelector(".go-back-dialog-heading")?.textContent).toBe("Go back to Panels?");
    expect(mount.querySelector(".go-back-dialog-body")?.textContent).toBe(
      "This discards 4 protected masks and re-runs bubble detection for the whole page.",
    );
    expect(mount.querySelector(".go-back-dialog-confirm")?.textContent).toBe("Go back and discard 4 edits");
    expect(mount.querySelector(".go-back-dialog-cancel")?.textContent).toBe("Stay on Protected");
  });

  it("does not render a target list for a single target", () => {
    openGoBackDialog(mount, [protectedTarget], vi.fn());
    expect(mount.querySelector(".go-back-dialog-targets")).toBeNull();
  });

  it("carries the destructive colour class on confirm and not on cancel", () => {
    openGoBackDialog(mount, [protectedTarget], vi.fn());

    const confirm = mount.querySelector(".go-back-dialog-confirm");
    const cancel = mount.querySelector(".go-back-dialog-cancel");
    expect(confirm?.classList.contains("destructive")).toBe(true);
    expect(cancel?.classList.contains("destructive")).toBe(false);
  });

  it("moves focus to the cancel button on open", () => {
    openGoBackDialog(mount, [protectedTarget], vi.fn());
    const cancel = mount.querySelector<HTMLButtonElement>(".go-back-dialog-cancel");
    expect(document.activeElement).toBe(cancel);
  });

  it("dismisses on Escape without calling onConfirm", () => {
    const onConfirm = vi.fn();
    openGoBackDialog(mount, [protectedTarget], onConfirm);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));

    expect(mount.children.length).toBe(0);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("dismisses on cancel click without calling onConfirm", () => {
    const onConfirm = vi.fn();
    openGoBackDialog(mount, [protectedTarget], onConfirm);

    mount.querySelector<HTMLButtonElement>(".go-back-dialog-cancel")!.click();

    expect(mount.children.length).toBe(0);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("calls onConfirm with the target's stage exactly once, even on a double-click", async () => {
    let resolveConfirm: () => void = () => {};
    const onConfirm = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveConfirm = resolve;
        }),
    );
    openGoBackDialog(mount, [protectedTarget], onConfirm);

    const confirmButton = mount.querySelector<HTMLButtonElement>(".go-back-dialog-confirm")!;
    confirmButton.click();
    confirmButton.click();

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("panels");
    expect(confirmButton.disabled).toBe(true);

    resolveConfirm();
    await vi.waitFor(() => {
      expect(mount.children.length).toBe(0);
    });
  });

  it("re-enables the confirm button and keeps the dialog open if onConfirm rejects", async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error("network error"));
    openGoBackDialog(mount, [protectedTarget], onConfirm);

    const confirmButton = mount.querySelector<HTMLButtonElement>(".go-back-dialog-confirm")!;
    confirmButton.click();

    await vi.waitFor(() => {
      expect(confirmButton.disabled).toBe(false);
    });
    expect(mount.children.length).toBeGreaterThan(0);
  });
});

describe("openGoBackDialog -- two targets", () => {
  it("renders a target list labelled with display_name and shows the selected target's sentence", () => {
    openGoBackDialog(mount, [protectedTarget, importTarget], vi.fn());

    const list = mount.querySelector(".go-back-dialog-targets");
    expect(list).not.toBeNull();
    const labels = Array.from(mount.querySelectorAll(".go-back-dialog-target")).map((el) => el.textContent);
    expect(labels).toEqual(["Panels", "Import"]);

    expect(mount.querySelector(".go-back-dialog-heading")?.textContent).toBe("Go back to Panels?");
  });

  it("changes heading, body and confirm label when the selection changes", () => {
    openGoBackDialog(mount, [protectedTarget, importTarget], vi.fn());

    const targets = mount.querySelectorAll<HTMLButtonElement>(".go-back-dialog-target");
    targets[1].click();

    expect(mount.querySelector(".go-back-dialog-heading")?.textContent).toBe("Go back to Import?");
    expect(mount.querySelector(".go-back-dialog-body")?.textContent).toBe(
      "This discards 6 panel polygons and 4 protected masks, and re-runs panel detection for the whole page.",
    );
    expect(mount.querySelector(".go-back-dialog-confirm")?.textContent).toBe("Go back and discard 10 edits");
    expect(mount.querySelector(".go-back-dialog-cancel")?.textContent).toBe("Stay on Panels");
  });

  it("confirms the currently-selected target's stage, not the first one", () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    openGoBackDialog(mount, [protectedTarget, importTarget], onConfirm);

    mount.querySelectorAll<HTMLButtonElement>(".go-back-dialog-target")[1].click();
    mount.querySelector<HTMLButtonElement>(".go-back-dialog-confirm")!.click();

    expect(onConfirm).toHaveBeenCalledWith("import");
  });
});

describe("openGoBackDialog -- teardown", () => {
  it("dismiss() removes the dialog and detaches the Escape listener", () => {
    const onConfirm = vi.fn();
    const dismiss = openGoBackDialog(mount, [protectedTarget], onConfirm);

    dismiss();
    expect(mount.children.length).toBe(0);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
