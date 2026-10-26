import { describe, expect, it } from "vitest";
import {
  HANDLED_KEYS,
  SHORTCUTS,
  SHORTCUT_GROUPS,
  shortcutKeys,
  withShortcut,
} from "./shortcuts";

// Keys handled outside the single-key editing switch (navigation / modifiers).
const NAVIGATION = new Set(["←", "→", "<", ">", "Esc"]);

describe("shortcut table", () => {
  it("lists exactly the single keys the editing handler implements", () => {
    const listed = new Set(
      Object.values(SHORTCUTS)
        .flatMap((s) => s.keys)
        .filter((k) => !NAVIGATION.has(k) && !/[⌘⇧]|Ctrl/.test(k))
        .map((k) => (k === "Space" ? " " : k.toLowerCase())),
    );
    expect([...listed].sort()).toEqual([...HANDLED_KEYS].sort());
  });
  it("shows every shortcut id in some panel group", () => {
    const shown = new Set(
      SHORTCUT_GROUPS.flatMap((g) => g.rows.map((r) => r.label)),
    );
    for (const s of Object.values(SHORTCUTS)) expect(shown).toContain(s.label);
  });
  it("formats tooltips", () => {
    expect(shortcutKeys("play")).toBe("Space / K");
    expect(withShortcut("添加回合", "markIn", "markOut")).toBe(
      "添加回合（I · O）",
    );
  });
});
