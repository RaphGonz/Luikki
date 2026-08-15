/**
 * The hash router: pure, testable route parsing plus a thin DOM-mounting
 * dispatcher. All four views are registered here (project picker, page
 * grid, page detail, palette) so plans 01-12 and 01-13 never need to edit
 * this file -- each of them only touches its own view module.
 */

import { renderPageDetail } from "../views/pageDetail";
import { renderPageGrid } from "../views/pageGrid";
import { renderPalette } from "../views/palette";
import { renderProjectPicker } from "../views/projectPicker";

export type Route =
  | { kind: "picker" }
  | { kind: "volume"; volumeId: number }
  | { kind: "page"; pageId: number }
  | { kind: "palette" };

/**
 * Total: an unknown, malformed or non-numeric-id hash falls back to the
 * picker route rather than dispatching with a bad id (T-01-HASH). A bad id
 * that *does* reach the API returns a neutral 404 from the routers
 * themselves.
 */
export function parseRoute(hash: string): Route {
  const trimmed = hash.replace(/^#\/?/, "");
  const parts = trimmed.split("/").filter((part) => part.length > 0);

  if (parts.length === 0) return { kind: "picker" };

  const [kind, idPart] = parts;

  if (kind === "picker") return { kind: "picker" };
  if (kind === "palette") return { kind: "palette" };

  if ((kind === "volume" || kind === "page") && idPart !== undefined) {
    const id = Number(idPart);
    if (Number.isInteger(id) && id >= 0) {
      return kind === "volume"
        ? { kind: "volume", volumeId: id }
        : { kind: "page", pageId: id };
    }
  }

  return { kind: "picker" };
}

/** The inverse of `parseRoute` for every valid route form. */
export function buildHash(route: Route): string {
  switch (route.kind) {
    case "picker":
      return "#/picker";
    case "volume":
      return `#/volume/${route.volumeId}`;
    case "page":
      return `#/page/${route.pageId}`;
    case "palette":
      return "#/palette";
  }
}

/** Sets `location.hash`, which drives `startRouter`'s `hashchange` listener. */
export function navigate(route: Route): void {
  location.hash = buildHash(route);
}

function dispatch(route: Route, mount: HTMLElement): () => void {
  switch (route.kind) {
    case "picker":
      return renderProjectPicker(mount);
    case "volume":
      return renderPageGrid(mount, { volumeId: route.volumeId });
    case "page":
      return renderPageDetail(mount, { pageId: route.pageId });
    case "palette":
      return renderPalette(mount);
  }
}

/**
 * Listens for `hashchange`, resolves the route to a view function, tears
 * down the previous view (each view returns a teardown callback) and
 * mounts the next.
 */
export function startRouter(mount: HTMLElement): void {
  let currentTeardown: (() => void) | null = null;

  const resolve = (): void => {
    const route = parseRoute(location.hash);
    currentTeardown?.();
    mount.replaceChildren();
    currentTeardown = dispatch(route, mount);
  };

  window.addEventListener("hashchange", resolve);
  resolve();
}
