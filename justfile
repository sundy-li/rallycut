# RallyCut 开发命令
#
#   just dev        启动原生桌面应用（缺依赖时自动准备）
#   just doctor     检查 ffmpeg / wails / node / uv 等外部依赖
#   just test       跑全部测试
#   just package    打包当前系统的桌面应用
#   just            显示全部命令

set shell := ["bash", "-euo", "pipefail", "-c"]
python := if os() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

# 列出可用命令
default:
    @just --list

# 首次准备 / 依赖变更后：Go 模块、前端依赖、Python 环境
setup:
    go mod download
    npm --prefix frontend ci
    uv venv --allow-existing --python 3.12 .venv
    uv pip install --python .venv/bin/python -r vision/requirements.txt

# 可选：安装模型依赖并下载权重（权重不随仓库分发）
setup-model:
    uv pip install --python .venv/bin/python -r vision/requirements-model.txt
    .venv/bin/python vision/download_model.py

# 启动 Wails 桌面应用；.venv / node_modules 缺失时先自动 setup
dev:
    #!/usr/bin/env bash
    if ! command -v wails >/dev/null 2>&1; then
      echo "未找到 wails CLI，请先安装：" >&2
      echo "  go install github.com/wailsapp/wails/v2/cmd/wails@v2.16.0" >&2
      exit 1
    fi
    if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import cv2, numpy' >/dev/null 2>&1 \
       || [ ! -d frontend/node_modules ]; then
      echo "首次启动，正在准备依赖（go mod / npm ci / uv venv）…"
      just setup
    fi
    command -v ffmpeg >/dev/null 2>&1 \
      || echo "提示：未找到 ffmpeg，分析与导出功能不可用（brew install ffmpeg）" >&2
    exec wails dev

# 仅前端界面预览（无 Go 接口与本机文件能力）
dev-web:
    npm --prefix frontend run dev

# 构建独立生产版 -> build/release/RallyCut.app（不受 wails dev 覆盖）
build:
    bash scripts/build-desktop.sh

# 生成平台加速模型：macOS Core ML（ANE）+ ONNX（Windows DirectML）
models:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "$(uname -s)" = "Darwin" ]; then
      {{python}} scripts/convert_blurball_coreml.py --out models/derived/BlurBall.mlpackage
    fi
    {{python}} scripts/export_blurball_onnx.py --out models/derived/BlurBall.onnx

# 用本地人工标注评估回合切分；真值文件不提交 Git
# 例：just evaluate /path/manual.json --candidate RallyCut=/tmp/ours.json --candidate TTcut=/tmp/ttcut.json
evaluate truth *candidates:
    {{python}} scripts/evaluate_rallies.py --truth "{{truth}}" {{candidates}}

# 私有标注库回测（RALLYCUT_LABELS_DIR 指向 rallycut-labels）：
#   just eval status | just eval cache（一次新鲜推理写 L0 缓存） | just eval run [--compare v15 --gate]
eval *args:
    {{python}} scripts/eval_labels.py {{args}}

# 打包当前系统的可分发桌面应用 -> build/release/
package:
    bash scripts/package.sh

# 打包 macOS 通用包（arm64 + x86_64，需在 macOS 上运行）
package-macos:
    bash scripts/package.sh macos

# 打包 Windows amd64（需在 Windows 上运行；安装 NSIS 后额外产安装器）
package-windows:
    bash scripts/package.sh windows

# 启动已构建的独立版；没有生产包时先构建，不依赖终端当前目录
run:
    #!/usr/bin/env bash
    if [ "$(uname -s)" != Darwin ]; then
      echo "just run 当前支持 macOS；其他平台请启动 build/bin 中的产物" >&2
      exit 1
    fi
    if [ ! -d build/release/RallyCut.app ]; then
      just build
    fi
    exec open -n "$PWD/build/release/RallyCut.app"

# 检查本机外部依赖与本地环境
doctor:
    #!/usr/bin/env bash
    missing=0
    check() {
      if command -v "$1" >/dev/null 2>&1; then
        printf '  ✓ %-8s %s\n' "$1" "$(command -v "$1")"
      else
        printf '  ✗ %-8s 未安装%s\n' "$1" "${2:+（$2）}"
        missing=1
      fi
    }
    echo "外部命令："
    check go
    check node
    check npm
    check uv "brew install uv"
    check ffmpeg "brew install ffmpeg"
    check ffprobe "brew install ffmpeg"
    check wails "go install github.com/wailsapp/wails/v2/cmd/wails@v2.16.0"
    echo "本地环境："
    if [ -x .venv/bin/python ] && .venv/bin/python -c 'import cv2, numpy' >/dev/null 2>&1; then
      echo "  ✓ .venv（Python 3.12 + OpenCV / NumPy）"
    else
      echo "  ✗ .venv 或 Python 依赖缺失（运行 just setup）"
      missing=1
    fi
    if [ -d frontend/node_modules ]; then
      echo "  ✓ frontend/node_modules"
    else
      echo "  ✗ frontend/node_modules 缺失（运行 just setup）"
      missing=1
    fi
    exit $missing

# 构建可独立安装的 coding-agent skill（不含权重、视频、桌面依赖）
skill:
    python3 scripts/build_skill.py

# 验证 skill 打包、精简 JSON、安全输出、跨目录运行
test-skill:
    python3 -m unittest discover -s tests/skills -v

# 全量测试：前端构建 + Go + Python + 前端单测
test:
    #!/usr/bin/env bash
    if ! { [ -x .venv/bin/python ] && .venv/bin/python -c 'import cv2, numpy' >/dev/null 2>&1; }; then
      echo "缺少 .venv 依赖，请先运行 just setup" >&2
      exit 1
    fi
    npm --prefix frontend run build
    go test -race ./...
    .venv/bin/python -m unittest discover -s vision/tests -v
    python3 -m unittest discover -s tests/skills -v
    npm --prefix frontend test

# 只跑 Go 测试（更快）
test-go:
    go test -race ./...

# 格式化 Go 与前端代码
fmt:
    gofmt -w main.go backend vision/embed.go tests/integration
    npm --prefix frontend run format

# 清理构建产物
clean:
    rm -rf build/bin build/release build/skills
