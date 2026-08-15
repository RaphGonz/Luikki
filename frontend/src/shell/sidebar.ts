/**
 * The persistent left sidebar (01-UI-SPEC.md §8): the project name at the
 * top, a collapsible Volume -> Page tree fetched via `api.volumes.list`
 * and `api.pages.list`, and a "Palette" entry point pinned beneath the
 * tree. Section headers use Label typography.
 *
 * Volume create, rename and delete live here as a kebab menu per row,
 * minimal per D-03 (volumes are artist-visible in the tree, nothing more).
 * The selected volume/page uses the accent current-item indicator -- one
 * of the three uses 01-UI-SPEC.md § Color reserves accent for, and nothing
 * else in the sidebar may use it.
 *
 * T-01-XSS: every artist-supplied or server-supplied string (project name,
 * volume name, page name) is inserted via `textContent`, never `innerHTML`.
 */

import { api } from "../api/client";
import type { PageDto, VolumeDto } from "../api/types";
import { navigate, type Route } from "./router";

interface VolumeRowState {
  volume: VolumeDto;
  expanded: boolean;
  pages: PageDto[] | null;
}

export function renderSidebar(mount: HTMLElement, currentRoute?: Route): () => void {
  const root = document.createElement("aside");
  root.className = "app-sidebar";

  const projectName = document.createElement("div");
  projectName.className = "sidebar-project-name";
  root.append(projectName);

  const sectionHeader = document.createElement("div");
  sectionHeader.className = "sidebar-section-header";
  sectionHeader.textContent = "Volumes";
  root.append(sectionHeader);

  const newVolumeButton = document.createElement("button");
  newVolumeButton.type = "button";
  newVolumeButton.className = "sidebar-new-volume";
  newVolumeButton.textContent = "New Volume";
  newVolumeButton.addEventListener("click", () => void createVolume());
  root.append(newVolumeButton);

  const tree = document.createElement("ul");
  tree.className = "sidebar-tree";
  root.append(tree);

  const paletteEntry = document.createElement("button");
  paletteEntry.type = "button";
  paletteEntry.className = "sidebar-palette-entry";
  paletteEntry.textContent = "Palette";
  if (currentRoute?.kind === "palette") {
    paletteEntry.classList.add("is-current");
  }
  paletteEntry.addEventListener("click", () => navigate({ kind: "palette" }));
  root.append(paletteEntry);

  mount.append(root);

  let disposed = false;
  const states = new Map<number, VolumeRowState>();

  function renderVolumeRow(state: VolumeRowState): HTMLElement {
    const li = document.createElement("li");
    li.className = "sidebar-volume-row";

    const row = document.createElement("div");
    row.className = "sidebar-row";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "sidebar-row-toggle";
    toggle.setAttribute(
      "aria-label",
      state.expanded ? `Collapse volume: ${state.volume.name}` : `Expand volume: ${state.volume.name}`,
    );
    toggle.textContent = state.expanded ? "−" : "+";
    toggle.addEventListener("click", () => void toggleVolume(state));
    row.append(toggle);

    const label = document.createElement("span");
    label.className = "sidebar-row-label";
    label.textContent = state.volume.name;
    if (currentRoute?.kind === "volume" && currentRoute.volumeId === state.volume.id) {
      label.classList.add("is-current");
    }
    label.addEventListener("click", () => navigate({ kind: "volume", volumeId: state.volume.id }));
    row.append(label);

    const kebab = document.createElement("button");
    kebab.type = "button";
    kebab.className = "sidebar-row-kebab";
    kebab.setAttribute("aria-label", `Volume options: ${state.volume.name}`);
    kebab.textContent = "⋮";
    kebab.addEventListener("click", () => toggleMenu(li, state));
    row.append(kebab);

    li.append(row);

    if (state.expanded) {
      const pageList = document.createElement("ul");
      pageList.className = "sidebar-page-list";
      if (state.pages) {
        for (const page of state.pages) {
          const pageItem = document.createElement("li");
          const pageLabel = document.createElement("span");
          pageLabel.className = "sidebar-page-label";
          pageLabel.textContent = page.original_name;
          if (currentRoute?.kind === "page" && currentRoute.pageId === page.id) {
            pageLabel.classList.add("is-current");
          }
          pageLabel.addEventListener("click", () => navigate({ kind: "page", pageId: page.id }));
          pageItem.append(pageLabel);
          pageList.append(pageItem);
        }
      }
      li.append(pageList);
    }

    return li;
  }

  function toggleMenu(li: HTMLElement, state: VolumeRowState): void {
    const existing = li.querySelector(".sidebar-row-menu");
    if (existing) {
      existing.remove();
      return;
    }

    const menu = document.createElement("div");
    menu.className = "sidebar-row-menu";

    const rename = document.createElement("button");
    rename.type = "button";
    rename.textContent = "Rename";
    rename.addEventListener("click", () => void renameVolume(state));
    menu.append(rename);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "sidebar-row-delete";
    del.setAttribute("aria-label", `Delete volume: ${state.volume.name}`);
    del.textContent = "Delete";
    del.addEventListener("click", () => void deleteVolume(state));
    menu.append(del);

    li.append(menu);
  }

  async function refresh(): Promise<void> {
    const [project, volumes] = await Promise.all([api.projects.current(), api.volumes.list()]);
    if (disposed) return;
    projectName.textContent = project.name;
    tree.replaceChildren();
    const seen = new Set<number>();
    for (const volume of volumes) {
      seen.add(volume.id);
      const state = states.get(volume.id) ?? { volume, expanded: false, pages: null };
      state.volume = volume;
      states.set(volume.id, state);
      tree.append(renderVolumeRow(state));
    }
    for (const id of [...states.keys()]) {
      if (!seen.has(id)) states.delete(id);
    }
  }

  async function toggleVolume(state: VolumeRowState): Promise<void> {
    state.expanded = !state.expanded;
    if (state.expanded && state.pages === null) {
      state.pages = await api.pages.list(state.volume.id);
    }
    await refresh();
  }

  async function createVolume(): Promise<void> {
    const name = window.prompt("Volume name", "Untitled Volume");
    if (!name) return;
    await api.volumes.create(name);
    await refresh();
  }

  async function renameVolume(state: VolumeRowState): Promise<void> {
    const name = window.prompt("Rename volume", state.volume.name);
    if (!name) return;
    await api.volumes.rename(state.volume.id, name);
    await refresh();
  }

  async function deleteVolume(state: VolumeRowState): Promise<void> {
    await api.volumes.remove(state.volume.id);
    states.delete(state.volume.id);
    await refresh();
  }

  void refresh();

  return () => {
    disposed = true;
  };
}
