# RallyCut logo

选定方向：**Timeline Bounce**（回合时间轴）——球的飞行轨迹压在剪辑时间轴上，
高亮的那一段就是留下来的回合。

沿用现有视觉语言：墨黑 `#111417`、青柠 `#c2ec94`、奶白 `#f3f7ee`；词标用应用自己的
UI 字面 `Avenir Next`（不是另找一款字体）。

```
design/logo/
├── generate.py            # 单一来源：改几何后重跑即覆盖 svg/ 与 final/
├── index.html             # 六个候选的画廊（含小尺寸与横版组合）
├── preview.png            # 一张图看全部候选
├── svg/                   # 候选：c1–c6 各自的 icon + lockup
├── final/                 # 选定方向的正式交付物
│   ├── rallycut-mark.svg              240×240，透明底（深色面上用）
│   ├── rallycut-mark-mono-lime.svg    单色青柠
│   ├── rallycut-mark-mono-ink.svg     单色墨黑（浅底用）
│   ├── rallycut-logo.svg              横版组合 560×160
│   ├── rallycut-appicon.svg           1024 应用图标（墨黑圆角底板 + 图形）
│   └── rallycut-appicon-{1024,512,256,128,64}.png
└── legacy/
    └── appicon-paddle.png   # 被替换掉的旧应用图标（球拍照）
```

## 图形构成

在 240×240 网格上：

- 飞行轨迹：`stroke-width 9.5`、`dasharray 10 12`、圆头端点，一段浅弧。
  虚线是**点线纹理**而不是粗虚线——粗虚线在大尺寸下会读成「阶梯」。
- 球：`r=18`，奶白实心，落在轨迹末端。
- 时间轴：5 段等高圆角条（`h=18`, `rx=9`），未选中 `opacity .3`，选中段为实心奶白。

图形内容的实际范围是 `x 20–210, y 70–180`（`generate.py` 里的 `MARK_BOX`）。
横版组合和应用图标都按这个范围居中，避免用整块 240 画布留白当排版。

## 重新生成

```bash
python3 design/logo/generate.py     # 需要 python3；PNG 需要 rsvg-convert（brew install librsvg）
```

`generate.py` 是唯一来源：改颜色、虚线密度、条形宽度后重跑，`svg/`、`index.html`、
`preview.png`、`final/` 会一起更新。

看画廊：直接打开 `design/logo/index.html`，或看 `preview.png`。

## 应用图标

`build/appicon.png` 已换成 `final/rallycut-appicon-1024.png`（1024×1024 RGBA，
圆角半径 225，与旧图标一致）。Wails 按约定读取这个路径，**重新构建或重启开发版后才会生效**：

```bash
just build && just run    # 生产版
just dev                  # 开发版（会覆盖 build/bin，不覆盖 build/appicon.png）
```

旧图标保留在 `design/logo/legacy/appicon-paddle.png`，要回退直接覆盖回去即可。

## 还没做

- **词标未转轮廓**：`rallycut-logo.svg` 里仍是 `<text font-family="Avenir Next">`，
  在没装该字体的机器（如 Linux/CI）上会回退。对外分发前需要用 fontTools 转成 path。
- **浅底完整版**：目前只有单色墨黑的 `mono-ink` 近似版，没有做「浅底 + 双色」的完整稿。
- **UI 内未接入**：应用头部 `.brand-mark` 仍是 CSS 手画的两根条 + 一个圆点
  （概念一致，但不是这个图形）。要统一需改 `frontend/src/App.tsx` 与 `style.css`，
  并同步 `tests/ui`。
- 没有 favicon / 启动图 / App Store 尺寸表。
