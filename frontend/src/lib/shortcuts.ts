// Single source of truth for the keyboard shortcuts shown to users: the
// shortcuts panel and button tooltips both read from here, so they cannot
// drift apart. The handlers themselves live in App.tsx; shortcuts.test.ts
// pins the table against the keys those handlers implement.

export const isMac =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

/** Display form of the platform command modifier. */
const mod = (key: string) => (isMac ? `⌘${key}` : `Ctrl+${key}`);

export type ShortcutId =
  | "play"
  | "skipBack"
  | "skipForward"
  | "slower"
  | "faster"
  | "prevRally"
  | "nextRally"
  | "previewRally"
  | "markIn"
  | "markOut"
  | "cancelMark"
  | "setStart"
  | "setEnd"
  | "split"
  | "merge"
  | "delete"
  | "invalid"
  | "favorite"
  | "undo"
  | "redo"
  | "openProject"
  | "settings"
  | "shortcuts";

export interface Shortcut {
  /** Alternative key combos, each already in display form. */
  keys: string[];
  label: string;
}

export const SHORTCUTS: Record<ShortcutId, Shortcut> = {
  play: { keys: ["Space", "K"], label: "播放 / 暂停" },
  skipBack: { keys: ["←"], label: "按步长后退" },
  skipForward: { keys: ["→"], label: "按步长前进" },
  slower: { keys: ["<"], label: "降低预览倍速" },
  faster: { keys: [">"], label: "提高预览倍速" },
  prevRally: { keys: ["J"], label: "上一个回合" },
  nextRally: { keys: ["L"], label: "下一个回合" },
  previewRally: { keys: ["Enter"], label: "预览当前回合" },
  markIn: { keys: ["I"], label: "标记回合开始" },
  markOut: { keys: ["O"], label: "标记结束并添加回合" },
  cancelMark: { keys: ["Esc"], label: "取消标记" },
  setStart: { keys: ["["], label: "当前回合起点移到播放头" },
  setEnd: { keys: ["]"], label: "当前回合终点移到播放头" },
  split: { keys: ["S"], label: "在播放头拆分当前回合" },
  merge: { keys: ["M"], label: "合并已勾选的相邻回合" },
  delete: { keys: ["D"], label: "删除当前回合" },
  invalid: { keys: ["X"], label: "标记 / 取消无效分" },
  favorite: { keys: ["F"], label: "标记 / 取消精彩" },
  undo: { keys: [mod("Z")], label: "撤销" },
  redo: {
    keys: isMac ? ["⇧⌘Z"] : ["Ctrl+Shift+Z", "Ctrl+Y"],
    label: "重做",
  },
  openProject: { keys: [mod("O")], label: "打开项目" },
  settings: { keys: [mod(",")], label: "设置" },
  shortcuts: { keys: [mod("/")], label: "快捷键" },
};

export interface ShortcutRow {
  keys: string[];
  label: string;
}
export interface ShortcutGroup {
  title: string;
  note?: string;
  rows: ShortcutRow[];
}

const rows = (...ids: ShortcutId[]): ShortcutRow[] =>
  ids.map((id) => SHORTCUTS[id]);

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "播放",
    rows: rows(
      "play",
      "skipBack",
      "skipForward",
      "slower",
      "faster",
      "prevRally",
      "nextRally",
      "previewRally",
    ),
  },
  {
    title: "标记与编辑",
    rows: rows(
      "markIn",
      "markOut",
      "cancelMark",
      "setStart",
      "setEnd",
      "split",
      "merge",
      "delete",
      "invalid",
      "favorite",
      "undo",
      "redo",
    ),
  },
  {
    title: "进度条",
    note: "点中进度条后生效",
    rows: [
      { keys: ["←", "→"], label: "后退 / 前进 1 秒" },
      {
        keys: isMac ? ["⇧←", "⇧→"] : ["Shift+←", "Shift+→"],
        label: "后退 / 前进 5 秒",
      },
      { keys: ["Home", "End"], label: "跳到开头 / 结尾" },
    ],
  },
  {
    title: "项目",
    rows: rows("openProject", "settings", "shortcuts"),
  },
  {
    title: "鼠标",
    rows: [
      { keys: ["双击回合时间"], label: "修改起止点" },
      { keys: ["右键回合卡片"], label: "无效分 / 精彩 / 拆分 / 删除" },
      { keys: ["单击画面"], label: "播放 / 暂停" },
      { keys: ["拖动进度条"], label: "定位播放位置" },
      { keys: ["双击项目名"], label: "重命名项目" },
    ],
  },
];

/** "Space / K" — the display form used inside tooltips. */
export function shortcutKeys(id: ShortcutId): string {
  return SHORTCUTS[id].keys.join(" / ");
}

/** Tooltip text with the shortcut appended, e.g. "播放（Space / K）". */
export function withShortcut(label: string, ...ids: ShortcutId[]): string {
  return `${label}（${ids.map(shortcutKeys).join(" · ")}）`;
}

/**
 * Single keys the editing handler in App.tsx claims (preventDefault). Shared
 * so the shortcuts panel cannot list a letter the handler does not implement.
 */
export const HANDLED_KEYS = [
  " ",
  "enter",
  "i",
  "o",
  "s",
  "m",
  "d",
  "f",
  "j",
  "k",
  "l",
  "x",
  "[",
  "]",
] as const;
