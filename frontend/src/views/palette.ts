/**
 * The palette screen (PAL-01, PAL-02, PAL-03, PAL-04): swatch upload and
 * its extraction result, hand create/rename/recolour/delete, and the
 * character-sheet proposal review -- all on one view, because
 * 01-UI-SPEC.md's Phase-Specific Interaction Contracts §4 is emphatic
 * there is no separate "review extraction" screen distinct from "the
 * palette" (D-15). §5 layers the sheet proposals onto the same screen as
 * visually distinct dashed cards. The swatch grid at full 120x120 is the
 * screen's one visual anchor (§8) -- nothing else here carries a
 * saturated colour except the swatches/proposal chips and the single
 * accent CTA.
 *
 * T-01-XSS: every artist-supplied or server-supplied string (labels,
 * character names, error details) is set via `.textContent`/`.value`;
 * raw-markup insertion is grep-asserted absent from this file.
 */

import "../styles/palette.css";

import { api, ApiError } from "../api/client";
import type { PaletteEntryDto, ProposalDto, RGBTuple } from "../api/types";
import { showToast } from "../components/toast";
import {
  renderSwatchCard,
  type SwatchCardHandlers,
} from "../components/swatchCard";
import {
  acceptPayload,
  entryLabel,
  ProposalValidationError,
  renderProposalCard,
  type ProposalCardHandlers,
  type ProposalSelection,
} from "../components/proposalCard";

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

function rgbToHex([r, g, b]: RGBTuple): string {
  const channel = (n: number) => n.toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

interface ProposalUIState {
  selected: boolean;
  part: string;
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

  // ---- Character-sheet proposals (PAL-02) --------------------------------

  let sheetId: string | null = null;
  let proposals: ProposalDto[] = [];
  const proposalState = new Map<number, ProposalUIState>();
  const previewSpans = new Map<number, HTMLElement>();

  const sheetError = document.createElement("div");
  sheetError.className = "palette-error";
  sheetError.hidden = true;

  const sheetDrop = document.createElement("div");
  sheetDrop.className = "palette-dropzone";
  const sheetDropText = document.createElement("p");
  sheetDropText.textContent =
    "Drop a character sheet — we'll propose colours from it.";
  const sheetInput = document.createElement("input");
  sheetInput.type = "file";
  sheetInput.accept = "image/*";
  sheetInput.className = "palette-dropzone-input";
  sheetDrop.append(sheetDropText, sheetInput);

  const sheetImage = document.createElement("img");
  sheetImage.className = "palette-sheet-image";
  sheetImage.alt = "Uploaded character sheet";
  sheetImage.hidden = true;

  const discardSheetButton = document.createElement("button");
  discardSheetButton.type = "button";
  discardSheetButton.className = "palette-discard-sheet destructive";
  discardSheetButton.textContent = "Discard sheet";
  discardSheetButton.hidden = true;

  const proposalGrid = document.createElement("div");
  proposalGrid.className = "proposal-grid";

  const acceptForm = document.createElement("div");
  acceptForm.className = "accept-form";
  acceptForm.hidden = true;

  const characterNameInput = document.createElement("input");
  characterNameInput.type = "text";
  characterNameInput.className = "accept-form-character";
  characterNameInput.placeholder = "e.g. Kaito";
  characterNameInput.setAttribute("aria-label", "Character name");

  const acceptFormEntries = document.createElement("div");
  acceptFormEntries.className = "accept-form-entries";

  const acceptSubmit = document.createElement("button");
  acceptSubmit.type = "button";
  acceptSubmit.className = "accept-form-submit accent";
  acceptSubmit.textContent = "Accept";

  acceptForm.append(characterNameInput, acceptFormEntries, acceptSubmit);

  root.append(
    sheetError,
    sheetDrop,
    sheetImage,
    discardSheetButton,
    proposalGrid,
    acceptForm,
  );

  function showSheetError(detail: string): void {
    sheetError.textContent = detail;
    sheetError.hidden = false;
  }

  function clearSheetError(): void {
    sheetError.hidden = true;
    sheetError.textContent = "";
  }

  sheetInput.addEventListener("change", () => {
    const file = sheetInput.files?.[0];
    if (file) void uploadSheet(file);
    sheetInput.value = "";
  });
  sheetDrop.addEventListener("dragover", (event) => event.preventDefault());
  sheetDrop.addEventListener("drop", (event) => {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (file) void uploadSheet(file);
  });

  async function uploadSheet(file: File): Promise<void> {
    try {
      const result = await api.references.uploadSheet(file);
      sheetId = result.sheet_id;
      proposals = result.proposals;
      proposalState.clear();
      for (const proposal of proposals) {
        proposalState.set(proposal.index, { selected: false, part: "" });
      }
      sheetImage.src = result.image_url;
      sheetImage.hidden = false;
      discardSheetButton.hidden = false;
      renderProposalGrid();
      updateAcceptForm();
      clearSheetError();
    } catch (err) {
      if (err instanceof ApiError) showSheetError(err.detail);
    }
  }

  const proposalHandlers: ProposalCardHandlers = {
    onToggleSelect: (index, selected) => {
      const state = proposalState.get(index);
      if (state) state.selected = selected;
      updateAcceptForm();
    },
    onAccept: (index) => {
      const state = proposalState.get(index);
      if (state) state.selected = true;
      renderProposalGrid();
      updateAcceptForm();
    },
    onReject: (index) => {
      proposals = proposals.filter((p) => p.index !== index);
      proposalState.delete(index);
      renderProposalGrid();
      updateAcceptForm();
    },
  };

  function renderProposalGrid(): void {
    proposalGrid.replaceChildren();
    for (const proposal of proposals) {
      const selected = proposalState.get(proposal.index)?.selected ?? false;
      renderProposalCard(proposalGrid, proposal, selected, proposalHandlers);
    }
  }

  function refreshPreviews(): void {
    for (const [index, span] of previewSpans) {
      const state = proposalState.get(index);
      span.textContent = entryLabel(characterNameInput.value, state?.part ?? "");
    }
  }
  characterNameInput.addEventListener("input", refreshPreviews);

  function updateAcceptForm(): void {
    const selected = proposals.filter(
      (p) => proposalState.get(p.index)?.selected,
    );
    if (selected.length === 0) {
      acceptForm.hidden = true;
      acceptFormEntries.replaceChildren();
      previewSpans.clear();
      return;
    }

    acceptForm.hidden = false;
    acceptFormEntries.replaceChildren();
    previewSpans.clear();

    for (const proposal of selected) {
      const state = proposalState.get(proposal.index);
      if (!state) continue;

      const row = document.createElement("div");
      row.className = "accept-form-row";

      const swatch = document.createElement("span");
      swatch.className = "accept-form-row-colour";
      swatch.style.background = rgbToHex(proposal.rgb);

      const partInput = document.createElement("input");
      partInput.type = "text";
      partInput.placeholder = "e.g. hair, base, eyes";
      partInput.setAttribute(
        "aria-label",
        `Part for proposal ${proposal.index + 1}`,
      );
      partInput.value = state.part;
      partInput.addEventListener("input", () => {
        state.part = partInput.value;
        preview.textContent = entryLabel(characterNameInput.value, state.part);
      });

      const preview = document.createElement("span");
      preview.className = "accept-form-row-preview";
      preview.textContent = entryLabel(characterNameInput.value, state.part);
      previewSpans.set(proposal.index, preview);

      row.append(swatch, partInput, preview);
      acceptFormEntries.append(row);
    }
  }

  acceptSubmit.addEventListener("click", () => void submitAccept());

  async function submitAccept(): Promise<void> {
    if (!sheetId) return;

    const selection: ProposalSelection = {
      characterName: characterNameInput.value,
      entries: proposals.map((p) => {
        const state = proposalState.get(p.index);
        return {
          index: p.index,
          selected: state?.selected ?? false,
          part: state?.part ?? "",
        };
      }),
    };

    let payload;
    try {
      payload = acceptPayload(selection);
    } catch (err) {
      if (err instanceof ProposalValidationError) showSheetError(err.message);
      return;
    }

    try {
      const result = await api.references.accept(
        sheetId,
        payload.character_name,
        payload.items,
      );
      for (const entry of result.entries) {
        entries.push(entry);
        renderSwatchCard(grid, entry, swatchHandlers);
      }
      const acceptedIndices = new Set(payload.items.map((item) => item.index));
      proposals = proposals.filter((p) => !acceptedIndices.has(p.index));
      for (const index of acceptedIndices) proposalState.delete(index);
      renderProposalGrid();
      updateAcceptForm();
      clearSheetError();
    } catch (err) {
      // The artist's typed character name and parts stay in the fields --
      // acceptForm is not rebuilt on failure (UI-SPEC §7).
      if (err instanceof ApiError) showSheetError(err.detail);
    }
  }

  discardSheetButton.addEventListener("click", () => void discardSheet());

  async function discardSheet(): Promise<void> {
    if (!sheetId) return;
    try {
      await api.references.discard(sheetId);
    } catch (err) {
      if (err instanceof ApiError) showSheetError(err.detail);
      return;
    }
    sheetId = null;
    proposals = [];
    proposalState.clear();
    sheetImage.hidden = true;
    discardSheetButton.hidden = true;
    renderProposalGrid();
    updateAcceptForm();
    clearSheetError();
  }

  void loadPalette();

  return () => {
    disposed = true;
    root.remove();
  };
}
