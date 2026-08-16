/**
 * TypeScript interfaces mirroring `src/comiccolor/web/schemas.py`'s Pydantic
 * response/request models, field-for-field. Declared once here -- plans
 * 01-12 and 01-13 build against this file directly rather than adding a DTO
 * of their own, which is what keeps them out of this module's git history.
 *
 * `stage` is typed as the closed string union of the eight `PipelineStage`
 * values (`src/comiccolor/model/entities.py`), not a free-form `string`, so
 * an unexpected value fails to compile rather than silently rendering
 * nothing in the stage strip.
 */

export type PipelineStageName =
  | "import"
  | "panels"
  | "protected"
  | "zones"
  | "propose"
  | "snap"
  | "review"
  | "export";

/** Three 0..255 channels, matching `schemas.py`'s `RGBTuple`. */
export type RGBTuple = [number, number, number];

// ---- Projects ---------------------------------------------------------

export interface ProjectDto {
  id: number;
  name: string;
  path: string;
  palette_revision: number;
}

export interface RecentProjectDto {
  name: string;
  path: string;
  opened_at: string;
}

export interface BrowseDto {
  path: string;
}

// ---- Volumes ------------------------------------------------------------

export interface VolumeDto {
  id: number;
  project_id: number;
  name: string;
  page_count: number;
}

// ---- Pages ----------------------------------------------------------------

export interface PageDto {
  id: number;
  volume_id: number;
  index: number;
  original_name: string;
  width: number;
  height: number;
  stage: PipelineStageName;
  // Server-built `/api/pages/{id}/image` path -- the frontend never
  // constructs a filesystem path and the on-disk name never reaches here.
  image_url: string;
}

export interface RejectedUploadDto {
  filename: string;
  detail: string;
}

export interface PageUploadDto {
  accepted: PageDto[];
  rejected: RejectedUploadDto[];
}

// ---- Pipeline -------------------------------------------------------------

export interface StageDto {
  name: PipelineStageName;
  display_name: string;
  upstream: PipelineStageName | null;
  produces: string;
  has_runner: boolean;
}

// ---- Palette --------------------------------------------------------------

export interface PaletteEntryDto {
  id: number;
  rgb: RGBTuple;
  label: string;
  entity_id: number | null;
  revision: number;
}

export interface PaletteUpdateDto {
  entry: PaletteEntryDto;
  // Feeds 01-UI-SPEC.md §6's "Updated on {N} page{s}" toast.
  pages_affected: number;
}

export interface SwatchExtractDto {
  entries: PaletteEntryDto[];
}

// ---- Character sheet proposals --------------------------------------------

export interface ProposalDto {
  // Proposals carry an index, not a database id -- nothing is persisted
  // until accept (D-05, RESEARCH.md § Anti-Patterns).
  index: number;
  rgb: RGBTuple;
  pixel_share: number;
}

export interface SheetProposalDto {
  sheet_id: string;
  image_url: string;
  proposals: ProposalDto[];
}

export interface SheetAcceptItemDto {
  index: number;
  part: string;
}

export interface SheetAcceptDto {
  entity_id: number;
  entries: PaletteEntryDto[];
}

// ---- Panels -----------------------------------------------------------

/** A single `[x, y]` page-space pixel coordinate, matching `schemas.py`'s `Vertex`. */
export type VertexDto = [number, number];

export interface PanelDto {
  id: number;
  page_id: number;
  x: number;
  y: number;
  width: number;
  height: number;
  reading_order: number;
  polygon: VertexDto[];
}

/**
 * A page's whole panel list. Every mutating panel route returns this rather
 * than the single changed panel -- the server owns reading order and
 * recomputes it on each mutation (`_recompute_reading_order`), so the client
 * renders what it is given and never renumbers locally.
 */
export interface PanelListDto {
  panels: PanelDto[];
}

// ---- Protected masks ----------------------------------------------------

export type ProtectedKindDto = "bubble" | "sfx";

export interface ProtectedMaskDto {
  id: number;
  page_id: number;
  kind: ProtectedKindDto;
  polygon: VertexDto[];
  // UI-SPEC §3: false renders a dashed outline (detector-proposed and
  // untouched), true renders solid (hand-drawn or reshaped).
  touched: boolean;
  area: number;
  bbox: [number, number, number, number];
}

export interface ProtectedMaskListDto {
  masks: ProtectedMaskDto[];
  // UI-SPEC §4's copy: bubble detection failing is a non-blocking inline
  // banner, never a blocking error -- PROT-02's hand-drawing is the
  // guaranteed fallback.
  detection_failed: boolean;
  detection_message: string | null;
}

// ---- Pipeline stage confirmation -----------------------------------------

export interface StageConfirmDto {
  page: PageDto;
  detection_failed: boolean;
  detection_message: string | null;
}

/**
 * 01-UI-SPEC.md §3: every one of these strings is server-computed from real
 * counts at the moment the dialog opens; a target whose count cannot be
 * computed is simply not returned, and the client never assembles a
 * sentence itself.
 */
export interface GoBackTargetDto {
  stage: PipelineStageName;
  display_name: string;
  heading: string;
  body: string;
  confirm_label: string;
  cancel_label: string;
  discarded_count: number;
}
