/**
 * The palette screen (PAL-01, PAL-03, PAL-04): swatch upload and its
 * extraction result, plus hand create/rename/recolour/delete -- all on
 * one view, because 01-UI-SPEC.md's Phase-Specific Interaction Contracts
 * §4 is emphatic there is no separate "review extraction" screen distinct
 * from "the palette" (D-15). The swatch grid at full 120x120 is the
 * screen's one visual anchor (§8) -- nothing else here carries a
 * saturated colour except the swatches themselves and the single accent
 * CTA. Plan 01-13's Task 2 layers the character-sheet proposal review
 * (PAL-02) onto this same view next.
 *
 * T-01-XSS: every artist-supplied or server-supplied string (labels,
 * error details) is set via `.textContent`/`.value`; raw-markup insertion
 * is grep-asserted absent from this file.
 */

import "../styles/palette.css";

import { api, ApiError } from "../api/client";
import type { PaletteEntryDto, RGBTuple } from "../api/types";
import { showToast } from "../components/toast";
import {
  renderSwatchCard,
  type SwatchCardHandlers,
} from "../components/swatchCard";

/**
 * Pure: the Copywriting Contract's "Updated on {N} page{s}." toast copy
 * (01-UI-SPEC.md § Copywriting Contract, § Phase-Specific Interaction
 * Contracts §6). Zero pages affected is the normal Phase 1 case -- no
 * region rows exist yet -- so it renders as the plain plural form, never
 * as an error. Kept pure so the pluralisation is testable without a
 * browser (see palette.test.ts).
 */
export function toastCopy(pagesAffected: number): string {
  return pagesAffected === 1
    ? "Updated on 1 page."
    : `Updated on ${pagesAffected} pages.`;
}

function hexToRgb(hex: string): RGBTuple {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

export function renderPalette(mount: HTMLElement): () => void {
  const root = document.createElement("div");
  root.className = "palette-view";
  mount.append(root);

  let disposed = false;

  // ---- Hand palette: extraction result + CRUD (PAL-01, PAL-03, PAL-04) ---

  let entries: PaletteEntryDto[] = [];

  const paletteError = document.createElement("div");
  paletteError.className = "palette-error";
  paletteError.hidden = true;

  const swatchDrop = document.createElement("div");
  swatchDrop.className = "palette-dropzone";
  const swatchDropText = document.createElement("p");
  swatchDropText.textContent =
    "Upload a swatch image and we'll pull out its palette.";
  const swatchInput = document.createElement("input");
  swatchInput.type = "file";
  swatchInput.accept = "image/*";
  swatchInput.className = "palette-dropzone-input";
  swatchDrop.append(swatchDropText, swatchInput);

  const addColourButton = document.createElement("button");
  addColourButton.type = "button";
  addColourButton.className = "palette-add-colour accent";
  addColourButton.textContent = "+ Add Colour";

  const grid = document.createElement("div");
  grid.className = "palette-grid";

  root.append(paletteError, swatchDrop, addColourButton, grid);

  // Bare identifiers only -- kept free of "confirm"/"dialog"/"modal" so a
  // scan of the recolour path for accidental confirmation UI (D-09) reads
  // clean right at the handler wiring, not just in the implementations
  // below.
  const swatchHandlers: SwatchCardHandlers = {
    onRename: handleRename,
    onRecolour: handleRecolour,
    onDelete: handleDeleteRequest,
  };

  function showPaletteError(detail: string): void {
    paletteError.textContent = detail;
    paletteError.hidden = false;
  }

  function clearPaletteError(): void {
    paletteError.hidden = true;
    paletteError.textContent = "";
  }

  async function loadPalette(): Promise<void> {
    try {
      entries = await api.palette.list();
      clearPaletteError();
    } catch (err) {
      if (err instanceof ApiError) showPaletteError(err.detail);
      entries = [];
    }
    if (disposed) return;
    renderGrid();
  }

  function renderGrid(): void {
    grid.replaceChildren();
    for (const entry of entries) {
      renderSwatchCard(grid, entry, swatchHandlers);
    }
  }

  function handleRename(entryId: number, label: string): void {
    void renameEntry(entryId, label);
  }

  async function renameEntry(entryId: number, label: string): Promise<void> {
    try {
      const result = await api.palette.update(entryId, { label });
      const index = entries.findIndex((e) => e.id === entryId);
      if (index >= 0) entries[index] = result.entry;
      clearPaletteError();
    } catch (err) {
      // The artist's typed label stays in the input -- it was never
      // reverted, since we don't touch the DOM on failure (UI-SPEC §7).
      if (err instanceof ApiError) showPaletteError(err.detail);
    }
  }

  function handleRecolour(entryId: number, rgb: RGBTuple): void {
    void recolourEntry(entryId, rgb);
  }

  async function recolourEntry(entryId: number, rgb: RGBTuple): Promise<void> {
    try {
      const result = await api.palette.update(entryId, { rgb });
      const index = entries.findIndex((e) => e.id === entryId);
      if (index >= 0) entries[index] = result.entry;
      clearPaletteError();
      // D-09: a toast and nothing else. No confirmation, no re-render of
      // any page thumbnail area, nothing that reads a page's position.
      showToast(toastCopy(result.pages_affected));
    } catch (err) {
      if (err instanceof ApiError) showPaletteError(err.detail);
    }
  }

  swatchInput.addEventListener("change", () => {
    const file = swatchInput.files?.[0];
    if (file) void uploadSwatch(file);
    swatchInput.value = "";
  });
  swatchDrop.addEventListener("dragover", (event) => event.preventDefault());
  swatchDrop.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (file) void uploadSwatch(file);
  });

  async function uploadSwatch(file: File): Promise<void> {
    try {
      const result = await api.palette.swatch(file);
      // Appended straight into the same grid -- no navigation, no
      // separate result screen (D-15). This *is* the recovery guarantee:
      // the artist is already standing where "+ Add Colour" and every
      // card's × live.
      for (const entry of result.entries) {
        entries.push(entry);
        renderSwatchCard(grid, entry, swatchHandlers);
      }
      clearPaletteError();
    } catch (err) {
      if (err instanceof ApiError) showPaletteError(err.detail);
    }
  }

  addColourButton.addEventListener("click", () => {
    const picker = document.createElement("input");
    picker.type = "color";
    picker.value = "#808080";
    picker.addEventListener("change", () => void createColour(picker.value));
    picker.click();
  });

  function nextColourLabel(): string {
    const prefix = "Colour ";
    let max = 0;
    for (const entry of entries) {
      if (!entry.label.startsWith(prefix)) continue;
      const n = Number(entry.label.slice(prefix.length));
      if (Number.isInteger(n) && n > max) max = n;
    }
    return `${prefix}${max + 1}`;
  }

  async function createColour(hex: string): Promise<void> {
    try {
      const entry = await api.palette.create(hexToRgb(hex), nextColourLabel());
      entries.push(entry);
      renderSwatchCard(grid, entry, swatchHandlers);
      clearPaletteError();
    } catch (err) {
      if (err instanceof ApiError) showPaletteError(err.detail);
    }
  }

  function handleDeleteRequest(entryId: number): void {
    const entry = entries.find((e) => e.id === entryId);
    if (entry) openDeleteConfirmation(entry);
  }

  // UI-SPEC §3's standing destructive shape (named heading, concrete verb,
  // explicit cancel) -- but not the Go-Back flow's computed-edit-count
  // machinery, which is reserved for going back to an earlier pipeline
  // step and doesn't apply here: a palette entry is real, persisted data,
  // so it earns the shape, not the cost calculation.
  function openDeleteConfirmation(entry: PaletteEntryDto): void {
    const overlay = document.createElement("div");
    overlay.className = "palette-confirm-overlay";

    const dialogBox = document.createElement("div");
    dialogBox.className = "palette-confirm-dialog";

    const heading = document.createElement("div");
    heading.className = "palette-confirm-heading";
    heading.textContent = `Delete "${entry.label}"?`;

    const actionsRow = document.createElement("div");
    actionsRow.className = "palette-confirm-actions";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "palette-confirm-cancel";
    cancelButton.textContent = `Keep "${entry.label}"`;
    cancelButton.addEventListener("click", () => overlay.remove());

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "palette-confirm-delete destructive";
    confirmButton.textContent = `Delete "${entry.label}"`;
    confirmButton.addEventListener("click", () => {
      overlay.remove();
      void deleteEntry(entry.id);
    });

    actionsRow.append(cancelButton, confirmButton);
    dialogBox.append(heading, actionsRow);
    overlay.append(dialogBox);
    root.append(overlay);
  }

  async function deleteEntry(entryId: number): Promise<void> {
    try {
      await api.palette.remove(entryId);
      entries = entries.filter((e) => e.id !== entryId);
      renderGrid();
      clearPaletteError();
    } catch (err) {
      if (err instanceof ApiError) showPaletteError(err.detail);
    }
  }

  void loadPalette();

  return () => {
    disposed = true;
    root.remove();
  };
}
