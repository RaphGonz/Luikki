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
