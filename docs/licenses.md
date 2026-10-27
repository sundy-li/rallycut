# 许可证核验清单

已引入固定提交的 BlurBall 网络定义（MIT、保留 notices），并按用户请求从官方来源下载权重用于本地实测。权重未进入 Git / Go embed / 应用包；官方独立权重再分发条款仍待确认，不能把源码 MIT 当作所有权重 / 数据都已获得商用和分发许可。

| 组件 | 当前状态 | 发布前要求 |
| --- | --- | --- |
| BlurBall 源码 | 已固定 `2f0f5496f7ba4b5b1a36790749935121b2ce972d`，MIT；原始网络未改动 | 保留 `vision/vendor/blurball` 内 MIT / Microsoft / HRNet notices；核对最终发布包 |
| BlurBall 官方 `blurball_best` 权重 | 已本地下载，固定 SHA-256；官方目录未提供单独权重许可 | 仅显式本地安装用于验证，不捆绑；向作者确认独立权重 / 数据条款后才可考虑商用或再分发 |
| TrackNet | 未引入 | 若选择，单独核对代码、权重和训练数据许可 |
| PyTorch 2.8.0 / 2.2.2（Intel Mac） | 用户确认后下载到应用 venv；未捆绑 wheel | 核对 BSD-style 及 wheel 的第三方动态库 notices；若打包不得只看顶层许可 |
| Wails v2 | 依赖已锁定 | 核对其 MIT 及 Go 间接依赖的 notices |
| React / Vite / TypeScript / lucide-react | 依赖已锁定 | 以 lockfile 的实际版本生成第三方清单 |
| golang.org/x/image v0.41.0 | 依赖已锁定（BSD-3-Clause，Go 项目）；用于导出叠加的字体光栅化 | 发布时附带其 LICENSE |
| 系统中文字体（STHeiti / Hiragino / 宋体） | 运行时读取用户系统字体渲染“回合 NN”，不复制、不打包 | 不随应用分发字体文件；成片内嵌少量字形的使用需按字体许可确认 |
| FFmpeg / FFprobe | 优先复用本机版本；缺失时用户确认后下载 eugeneware/ffmpeg-static b6.1.1 对应平台构建，固定体积 / SHA-256，保存 `.LICENSE` 与构建来源 `.README` | 第三方平台构建不等于 FFmpeg 官方二进制；构建选项决定 LGPL / GPL 等义务。当前使用 libx264，自动下载不免除来源、许可与专利审查；不随安装包捆绑 |
| Python | 优先复用兼容本机解释器；缺失时通过 uv 下载独立 CPython 3.12.12 至应用目录 | 核对 python-build-standalone、PSF 及所带动态库 notices，不能只看解释器顶层许可；未捆绑到应用包 |
| uv 0.9.5 | 用户确认后下载平台可执行文件，固定 release / 体积 / SHA-256；仅用于应用目录中的 Python 准备，不注册系统 Python、不改全局 PATH | 保留 MIT / Apache-2.0 来源与许可引用（https://github.com/astral-sh/uv/tree/0.9.5）；更新版本时重新核对 |
| OpenCV / opencv-python-headless | 固定为 4.11.0.86；使用 wheel，未复制上游源码 | 核查 OpenCV Apache-2.0 及 wheel 中 FFmpeg / 第三方库 notices，打包前不能只看 Python 包许可 |
| NumPy | Apple Silicon / Windows 固定 2.2.6；Intel Mac 为 1.26.4，以兼容该平台最后的 PyTorch wheel | 核查 BSD-3-Clause 及 wheel 内动态库的分发 notices |
| 比赛视频 | 用户已提供 DJI 原片用于本地开发检查 | 收集素材授权、隐私与肖像权，不把私有原片提交 Git |

项目自身尚未指定对外发布许可证；添加公共 LICENSE 前需项目所有者确认。此文档不构成法律意见。
