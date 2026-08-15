import { describe, expect, it } from "vitest";

import { recentListModel } from "../src/views/projectPicker";
import type { RecentProjectDto } from "../src/api/types";

const recents: RecentProjectDto[] = [
  { name: "Kaito", path: "/projects/kaito", opened_at: "2026-08-10T10:00:00Z" },
  { name: "Moebius", path: "/projects/moebius", opened_at: "2026-08-14T10:00:00Z" },
  { name: "Junji", path: "/projects/junji", opened_at: "2026-08-12T10:00:00Z" },
];

describe("recentListModel", () => {
  it("orders rows most-recent-first", () => {
    const rows = recentListModel(recents);
    expect(rows.map((r) => r.name)).toEqual(["Moebius", "Junji", "Kaito"]);
  });

  it("selects exactly one row", () => {
    const rows = recentListModel(recents);
    expect(rows.filter((r) => r.selected)).toHaveLength(1);
  });

  it("selects the current project when one is open, even if not most recent", () => {
    const rows = recentListModel(recents, "/projects/junji");
    const selected = rows.find((r) => r.selected);
    expect(selected?.name).toBe("Junji");
  });

  it("selects the first (most recent) row when no project is open", () => {
    const rows = recentListModel(recents);
    expect(rows[0]?.selected).toBe(true);
  });

  it("returns an empty array for empty input without throwing", () => {
    expect(() => recentListModel([])).not.toThrow();
    expect(recentListModel([])).toEqual([]);
  });

  it("returns one RecentRow per input entry", () => {
    const rows = recentListModel(recents);
    expect(rows).toHaveLength(recents.length);
  });
});
