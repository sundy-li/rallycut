#!/usr/bin/env bash
# Build a distributable desktop package for the current OS.
# Usage: scripts/package.sh [auto|macos|windows]
set -euo pipefail
cd "$(dirname "$0")/.."

target="${1:-auto}"
if [[ "$target" == auto ]]; then
  case "$(uname -s)" in
    Darwin) target=macos ;;
    MINGW*|MSYS*|CYGWIN*) target=windows ;;
    *)
      echo "不支持的系统：$(uname -s)。请在 macOS 或 Windows 上打包。" >&2
      exit 1
      ;;
  esac
fi

command -v wails >/dev/null 2>&1 || {
  echo "缺少 wails CLI：go install github.com/wailsapp/wails/v2/cmd/wails@v2.16.0" >&2
  exit 1
}

version="${VERSION:-$(git describe --tags --always --dirty 2>/dev/null || echo 0.1.0)}"
version="${version#v}"
version="${version//\//-}"
out="build/release"
mkdir -p "$out"
rm -f "$out"/RallyCut-*.zip "$out"/RallyCut-*.exe

# A concurrent `wails dev` can overwrite build/bin with a dev binary; never ship that.
verify_production() {
  local binary="$1" tags
  if ! tags="$(go version -m "$binary" 2>/dev/null | awk '$1 == "build" && $2 ~ /^-tags=/ {print $2}')" || [[ -z "$tags" ]]; then
    echo "警告：无法读取 $binary 的构建标签，跳过 production 校验" >&2
    return 0
  fi
  if [[ ! "$tags" =~ (^|[=,])production([,[:space:]]|$) ]] || [[ "$tags" =~ (^|[=,])dev([,[:space:]]|$) ]]; then
    echo "拒绝打包非 production 构建：$binary（请退出 wails dev 后重试）" >&2
    return 1
  fi
}

case "$target" in
  macos)
    [[ "$(uname -s)" == Darwin ]] || {
      echo "macOS 包必须在 macOS 上构建。" >&2
      exit 1
    }
    echo "构建 macOS 通用包（arm64 + x86_64）…"
    wails build -clean -platform darwin/universal
    app="build/bin/RallyCut.app"
    verify_production "$app/Contents/MacOS/RallyCut"
    # Ad-hoc signature: required for Apple Silicon to launch an unsigned bundle.
    codesign --force --deep --sign - "$app"
    codesign --verify --deep --strict "$app"
    artifact="$out/RallyCut-${version}-macos-universal.zip"
    ditto -c -k --sequesterRsrc --keepParent "$app" "$artifact"
    echo "产物：$artifact"
    ;;
  windows)
    case "$(uname -s)" in
      MINGW*|MSYS*|CYGWIN*) ;;
      *)
        echo "Windows 包必须在 Windows 上构建（Wails 不支持从 macOS 交叉编译桌面应用）。" >&2
        exit 1
        ;;
    esac
    args=(-clean -platform windows/amd64)
    if command -v makensis >/dev/null 2>&1; then
      args+=(-nsis)
    else
      echo "提示：未找到 makensis（NSIS），只生成免安装 exe。"
    fi
    echo "构建 Windows amd64 包…"
    wails build "${args[@]}"
    verify_production build/bin/RallyCut.exe
    cp build/bin/RallyCut.exe "$out/RallyCut-${version}-windows-amd64.exe"
    if [[ -f build/runtime-output/RallyCut-runtime-windows-amd64.zip ]]; then
      cp build/runtime-output/RallyCut-runtime-windows-amd64.zip "$out/"
      cp build/runtime-output/runtime-bundle.json "$out/"
    fi
    echo "产物：$out/RallyCut-${version}-windows-amd64.exe"
    for installer in build/bin/*installer*.exe; do
      [[ -e "$installer" ]] || continue
      cp "$installer" "$out/RallyCut-${version}-windows-amd64-setup.exe"
      echo "产物：$out/RallyCut-${version}-windows-amd64-setup.exe"
    done
    ;;
  *)
    echo "未知目标：$target（可用：auto、macos、windows）" >&2
    exit 1
    ;;
esac

echo "版本：$version"
ls -lh "$out"
