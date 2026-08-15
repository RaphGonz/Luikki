/**
 * A fixed 56px strip: breadcrumb/title, and a slot a page-open view can
 * mount its stage strip into (plan 01-12). Phases 2 and 3 reuse this exact
 * strip for the canvas tool controls (select/draw/merge/split modes), so
 * it must never grow a per-screen custom height (01-UI-SPEC.md §8).
 */

export interface ToolbarHandle {
  setTitle(title: string): void;
  readonly slot: HTMLElement;
}

let currentHandle: ToolbarHandle | null = null;

export function renderToolbar(mount: HTMLElement): ToolbarHandle {
  const root = document.createElement("div");
  root.className = "app-toolbar";

  const title = document.createElement("div");
  title.className = "app-toolbar-title";
  root.append(title);

  const slot = document.createElement("div");
  slot.className = "app-toolbar-slot";
  root.append(slot);

  mount.append(root);

  const handle: ToolbarHandle = {
    setTitle(text: string) {
      title.textContent = text;
    },
    slot,
  };
  currentHandle = handle;
  return handle;
}

/**
 * The most recently rendered toolbar handle. `main.ts` mounts exactly one
 * toolbar for the app's whole lifetime and does not thread the returned
 * handle through the router, so a view that needs the stage-strip slot
 * (plan 01-12's page detail) reads it here instead of `renderToolbar`
 * gaining a second call site.
 */
export function getToolbarHandle(): ToolbarHandle {
  if (!currentHandle) {
    throw new Error("Toolbar has not been rendered yet — renderToolbar() must run first.");
  }
  return currentHandle;
}
