/**
 * A fixed 120x120 palette swatch card (01-UI-SPEC.md §4/§8's visual anchor
 * for the palette screen): a 96px colour block above a 24px label strip.
 * Reused unchanged for accepted character-sheet entries -- `palette.ts`
 * calls this same function for both extraction/hand-added entries and
 * accepted proposals, so there is exactly one card type in the real
 * palette grid -- and, per this plan's <output>, by Phase 6's
 * zone-reassignment review view.
 *
 * T-01-XSS: the label is set via `.value`, never via raw-markup injection.
 */

import type { PaletteEntryDto, RGBTuple } from "../api/types";

export interface SwatchCardHandlers {
  onRename: (entryId: number, label: string) => void;
  onRecolour: (entryId: number, rgb: RGBTuple) => void;
  onDelete: (entryId: number) => void;
}

function toHex([r, g, b]: RGBTuple): string {
  const channel = (n: number) => n.toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

function fromHex(hex: string): RGBTuple {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

/**
 * Builds one card and appends it to `mount`. Returns the card element so a
 * caller can remove it directly (e.g. after a successful delete) without
 * re-rendering the whole grid.
 */
export function renderSwatchCard(
  mount: HTMLElement,
  entry: PaletteEntryDto,
  handlers: SwatchCardHandlers,
): HTMLElement {
  const card = document.createElement("div");
  card.className = "swatch-card";

  // The colour block: a hidden native `<input type="color">` stacked over
  // a plain div so the whole 96px block is the picker's click target.
  const colour = document.createElement("div");
  colour.className = "swatch-card__colour";
  colour.style.background = toHex(entry.rgb);

  const picker = document.createElement("input");
  picker.type = "color";
  picker.value = toHex(entry.rgb);
  picker.className = "swatch-card__picker";
  picker.setAttribute("aria-label", `Recolour ${entry.label}`);

  // UI-SPEC §6: the swatch follows every drag frame for direct visual
  // feedback, but only one write lands, on close/blur -- never per frame.
  let lastCommittedHex = picker.value;
  const commitRecolour = (): void => {
    if (picker.value === lastCommittedHex) return;
    lastCommittedHex = picker.value;
    handlers.onRecolour(entry.id, fromHex(picker.value));
  };
  picker.addEventListener('input', () => {
    colour.style.background = picker.value;
  });
  picker.addEventListener('change', commitRecolour);
  picker.addEventListener('blur', commitRecolour);

  colour.append(picker);

  const labelStrip = document.createElement("div");
  labelStrip.className = "swatch-card__label";

  const labelInput = document.createElement("input");
  labelInput.type = "text";
  labelInput.className = "swatch-card__label-input";
  labelInput.value = entry.label;
  labelInput.setAttribute("aria-label", "Palette entry name");

  const commitRename = (): void => {
    const value = labelInput.value.trim();
    if (value && value !== entry.label) {
      handlers.onRename(entry.id, value);
    } else {
      // Empty or unchanged: revert to the last known-good label rather
      // than sending a no-op or blank rename.
      labelInput.value = entry.label;
    }
  };
  labelInput.addEventListener("blur", commitRename);
  labelInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      labelInput.blur();
    }
  });

  // Icon-only, labelled by what it does rather than its glyph (UI-SPEC
  // §8 accessibility): aria-label="Delete palette entry".
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.className = "swatch-card__delete";
  deleteButton.setAttribute("aria-label", "Delete palette entry");
  deleteButton.textContent = "×";
  deleteButton.addEventListener("click", () => handlers.onDelete(entry.id));

  labelStrip.append(labelInput, deleteButton);
  card.append(colour, labelStrip);
  mount.append(card);
  return card;
}
