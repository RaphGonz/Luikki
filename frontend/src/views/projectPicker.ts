/**
 * The screen an artist actually starts on (01-UI-SPEC.md §8): the
 * recent-projects list is the visual anchor, with the most-recent row
 * pre-selected -- getting back into yesterday's project without a file
 * dialog (D-04). "Create Project" is a secondary CTA below the list, not a
 * hero button.
 *
 * There is no separate `Route` kind for "project open, nothing else
 * selected yet" (`shell/router.ts`'s `Route` union only has picker /
 * volume / page / palette), so this same view covers both states: no
 * project open renders the recents list, and a project already open (on
 * load, or the moment one is opened/created here) renders 01-UI-SPEC.md
 * §8's "Project shell (empty)" prompt in place.
 */

import { api, ApiError } from "../api/client";
import type { RecentProjectDto } from "../api/types";
import { navigate } from "../shell/router";

export interface RecentRow {
  name: string;
  path: string;
  openedAt: string;
  selected: boolean;
}

/**
 * Pure: most-recent-first ordering, exactly one selected row (the current
 * project if one is open, otherwise the first/most-recent row), empty
 * input -> empty output, no exception. Kept out of the DOM code so
 * UI-SPEC §8's "most-recent row pre-selected" rule is testable in Vitest
 * without a browser.
 */
export function recentListModel(
  recents: RecentProjectDto[],
  currentPath?: string,
): RecentRow[] {
  if (recents.length === 0) return [];

  const sorted = [...recents].sort(
    (a, b) => Date.parse(b.opened_at) - Date.parse(a.opened_at),
  );

  const currentIndex = currentPath ? sorted.findIndex((r) => r.path === currentPath) : -1;
  const selectedIndex = currentIndex >= 0 ? currentIndex : 0;

  return sorted.map((row, index) => ({
    name: row.name,
    path: row.path,
    openedAt: row.opened_at,
    selected: index === selectedIndex,
  }));
}

export function renderProjectPicker(mount: HTMLElement): () => void {
  const root = document.createElement("div");
  root.className = "project-picker";
  mount.append(root);

  let disposed = false;

  void boot();

  async function boot(): Promise<void> {
    // GET /api/projects/recent never omits folders that no longer contain
    // project.db, and the frontend must never cache recents itself or try
    // to repair a missing entry (D-04: the folder is authoritative, the
    // index is merely convenient) -- so every load re-fetches from scratch.
    try {
      const current = await api.projects.current();
      if (!disposed) renderShellEmpty(current.name);
    } catch {
      if (!disposed) await renderPicker();
    }
  }

  function renderShellEmpty(projectName: string): void {
    root.replaceChildren();
    const heading = document.createElement("div");
    heading.className = "shell-empty-heading";
    heading.textContent = projectName;
    const body = document.createElement("div");
    body.className = "shell-empty-body";
    body.textContent = "Add a volume from the sidebar, or drop pages once you have one.";
    root.append(heading, body);
  }

  async function renderPicker(): Promise<void> {
    root.replaceChildren();

    const errorBanner = document.createElement("div");
    errorBanner.className = "project-picker-error";
    errorBanner.hidden = true;

    const listSection = document.createElement("div");
    listSection.className = "project-picker-list";

    const createHeading = document.createElement("div");
    createHeading.className = "project-picker-create-heading";
    createHeading.textContent = "Create Project";

    const nameField = document.createElement("input");
    nameField.type = "text";
    nameField.className = "project-picker-name-field";
    nameField.placeholder = "Project name";

    const parentField = document.createElement("input");
    parentField.type = "text";
    parentField.className = "project-picker-parent-field";
    parentField.placeholder = "Parent folder";

    const actionsRow = document.createElement("div");
    actionsRow.className = "project-picker-actions";

    const browseButton = document.createElement("button");
    browseButton.type = "button";
    browseButton.className = "project-picker-browse";
    browseButton.textContent = "Browse…";

    const createButton = document.createElement("button");
    createButton.type = "button";
    createButton.className = "project-picker-create-button accent";
    createButton.textContent = "Create Project";

    actionsRow.append(browseButton, createButton);

    root.append(
      errorBanner,
      listSection,
      createHeading,
      nameField,
      parentField,
      actionsRow,
    );

    function showError(detail: string): void {
      errorBanner.textContent = detail;
      errorBanner.hidden = false;
    }

    function clearError(): void {
      errorBanner.hidden = true;
      errorBanner.textContent = "";
    }

    async function drawList(): Promise<void> {
      let recents: RecentProjectDto[] = [];
      try {
        recents = await api.projects.recent();
      } catch (err) {
        if (err instanceof ApiError) showError(err.detail);
        return;
      }

      listSection.replaceChildren();
      const rows = recentListModel(recents);

      if (rows.length === 0) {
        // Empty state: no list above "Create Project" -- the Copywriting
        // Contract's primary CTA is already rendered below this section.
        const empty = document.createElement("div");
        empty.className = "project-picker-empty";
        empty.textContent = "No recent projects yet — create one below.";
        listSection.append(empty);
        return;
      }

      const list = document.createElement("ul");
      list.className = "project-picker-recent-list";
      for (const row of rows) {
        const item = document.createElement("li");
        item.className = "project-picker-recent-row";
        if (row.selected) item.classList.add("is-current");

        const name = document.createElement("span");
        name.className = "project-picker-recent-name";
        name.textContent = row.name;

        const path = document.createElement("span");
        path.className = "project-picker-recent-path";
        path.textContent = row.path;

        item.append(name, path);
        item.addEventListener("click", () => void openProject(row.path));
        list.append(item);
      }
      listSection.append(list);
    }

    async function openProject(path: string): Promise<void> {
      clearError();
      try {
        const project = await api.projects.open(path);
        navigate({ kind: "picker" });
        renderShellEmpty(project.name);
      } catch (err) {
        if (err instanceof ApiError) showError(err.detail);
      }
    }

    createButton.addEventListener("click", () => void createProject());

    async function createProject(): Promise<void> {
      const name = nameField.value.trim();
      if (!name) {
        showError("Name the project — every project needs a name before it can be created.");
        return;
      }
      clearError();
      try {
        const project = await api.projects.create(name, parentField.value.trim() || undefined);
        renderShellEmpty(project.name);
      } catch (err) {
        if (err instanceof ApiError) {
          showError(err.detail);
        }
        // The artist's typed name and parent folder stay in the fields --
        // never cleared or reverted on a failed create (UI-SPEC.md §7,
        // PROJ-05).
      }
    }

    browseButton.addEventListener("click", () => void browse());

    async function browse(): Promise<void> {
      clearError();
      try {
        const result = await api.projects.browse();
        if (result) {
          // 200 fills the parent-folder field.
          parentField.value = result.path;
        }
        // 204 (cancelled) does nothing at all.
      } catch (err) {
        // 503 shows BROWSE_UNAVAILABLE_DETAIL inline and leaves the
        // typed-path field usable -- err.detail is rendered verbatim, the
        // same as every other failure on this screen.
        if (err instanceof ApiError) showError(err.detail);
      }
    }

    await drawList();
  }

  return () => {
    disposed = true;
    root.remove();
  };
}
