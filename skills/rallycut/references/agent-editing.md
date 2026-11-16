# 二次剪辑参考（plan / export / brief）

## 输入文档

| `kind` | 来源 | 内容 |
|---|---|---|
| 无 `kind`，有 `schema_version` / `sources` | 桌面版项目 `*-rallycut.json` | 完整项目，含球轨迹；`--trajectory` 只能用它 |
| `rallycut.project_brief` | 桌面版“复制给 AI”，或 `brief --input <项目>` | 全部素材与回合、剪辑参数、导出设置；不含轨迹 |
| `rallycut.segments` | `analyze` / `from-project` | 单个素材的回合候选；缓冲默认 0.5 / 0.8 秒 |

所有素材都必须有 `path`、`duration`、`fingerprint`；导出前会重新计算原片指纹，不一致就拒绝。

## project_brief

```json
{"schema_version":1,"kind":"rallycut.project_brief","project_name":"…","project_path":"/…/x-rallycut.json",
 "rules":{"pre_roll":0.5,"post_roll":0.8,"min_duration":6},
 "export_settings":{"codec":"h264","encoder":"auto","bit_rate":0,"overlap":"merge"},
 "sources":[
 {"id":"18e1…","video":{"path":"/…/match.mp4","name":"match.mp4","fingerprint":"…","duration":3104.47,…},"analyzed":true,"rallies":[
  {"key":"18e1…/visual-00001","n":2,"id":"visual-00001","start":2.3,"end":6.933,"confidence":0.8,"score":38.4,
   "selected":true,"edited":false,"duration":4.633,"human":false,"start_reason":"live_ball_evidence","end_reason":"stroke_gap"}
 ]}
]}
```

以上是结构示例，不是识别结果。

- 时间是秒，在各自素材的时间轴上，精确到毫秒。
- `n` 是该素材内按开始时间排的编号，和桌面版回合卡片上的 01、02… 一致；`key` 在整个项目内唯一。
- `human: true` 表示用户添加（`manual-*`）或修改过（`edited`）。重叠处理 `--overlap human|machine|sequential` 按这个区分。
- `selected` 决定是否导出；`invalid` 的回合永远不导出；`favorite` 是用户收藏。
- `boundary_before` / `start_reason` / `end_reason` 是死球边界证据：导出时缓冲不会越过受保护的边界把相邻回合连成一段。修改时保留这些字段。
- `score` / `confidence` 是规则排序分，不是准确率，也不代表“精彩”。

可以直接编辑这份 JSON 再传给 `--input`：改 `selected`、`start`、`end`，删掉不要的回合，或改 `rules` 的缓冲。新加的回合需要唯一 `id`、`start < end`、时长 ≥ 0.04 秒且在素材时长内，建议 `id` 用 `manual-` 开头表示人工。改动只影响这次导出，不会写回桌面项目。

## export_plan（plan 的输出）

```json
{"kind":"rallycut.export_plan","rules":{"pre_roll":2,"post_roll":1,"min_duration":6},"export_settings":{…},
 "selected_rallies":10,"total_duration":148.2,
 "spans":[{"source":"18e1…","video":"/…/match.mp4","start":73.9,"end":90.7,"duration":16.8,"rallies":[11]}]}
```

每个 `span` 是成片里的一段：原片上的 `start`–`end`（已含缓冲、已合并重叠）。一段可能包含多个回合（缓冲或重叠导致合并）。多素材时按素材顺序拼接，并统一为 1080p / 30 fps。`export` 用同样的选项会渲染出完全相同的片段列表。

## 选项

| 选项 | 作用 |
|---|---|
| `--max-rallies N` | 全项目最多 N 个：收藏优先，然后分数高、时长长 |
| `--rallies k1,k2` | 只导出这些回合（`key` 或唯一的 `id`） |
| `--favorites-only` | 只导出收藏 |
| `--min-duration S` | 去掉短于 S 秒的回合 |
| `--pre-roll S` / `--post-roll S` | 每个回合前 / 后保留秒数，0–60 |
| `--overlap` | `merge`（默认）/ `sequential` / `human` / `machine` |
| `--codec` / `--encoder` / `--bit-rate` | `h264`·`hevc` / `auto`·`software` / 每秒比特，0 跟随原片 |
| `--rally-labels` / `--trajectory` | 烧录回合编号 / 球轨迹（轨迹仅项目文件） |
| `--output` | 仅 export：`.mp4` 路径；已存在则失败 |
| `--overwrite` | 仅 export：用户明确要求替换已有成片时才加；新文件完整导出并校验后才替换，失败或取消时旧文件不变；原片永远不能被覆盖 |

筛选顺序：先按 `--rallies`（若给）重设选中，再去掉 `invalid`、非收藏（`--favorites-only`）和过短的，最后应用 `--max-rallies`。

## 错误与退出码

0 成功；1 输入无效、原片变化、没有选中回合、FFmpeg 失败；2 参数错误；130 取消。错误是 stderr 上的 `{"status":"failed","error":"…"}`，原样转告用户，不要换别的方法强行导出。回合编号烧录需要系统中文字体：macOS 自带，Linux 需安装 Noto Sans CJK；找不到字体会报错，去掉 `--rally-labels` 即可。
