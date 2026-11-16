#!/usr/bin/env bash
# Install the rallycut agent skill into the agent skills directories.
#
#   curl -fsSL https://raw.githubusercontent.com/sundy-li/rallycut/main/scripts/install-skill.sh | bash
#   bash install-skill.sh [--dir <skills dir>]... [--version <release tag>] [--from-source <repo dir>]
#
# Without --dir it installs into every agent that is present: ~/.claude/skills
# (Claude Code), ~/.codex/skills (Codex) and always ~/.agents/skills. The
# package comes from the newest GitHub Release that ships
# rallycut-skill-<version>.skill and is checked against that release's
# SHA256SUMS-macos.txt. Nothing is installed outside the skills directories;
# model weights are downloaded later only when the agent runs `setup`.
set -euo pipefail

REPO="sundy-li/rallycut"
NAME="rallycut"
# Mainland-China GitHub download accelerators, tried after the direct URL.
MIRRORS=("" "https://edgeone.gh-proxy.com/" "https://ghfast.top/" "https://hk.gh-proxy.com/" "https://gh-proxy.org/")

dirs=()
version=""
source_repo=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) dirs+=("$2"); shift 2 ;;
    --version) version="$2"; shift 2 ;;
    --from-source) source_repo="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || { say "需要 $1：$2"; exit 1; }; }

need python3 "rallycut skill 的启动器使用系统 Python 3"
need unzip "用于解压 .skill 包"
if command -v shasum >/dev/null 2>&1; then sha256() { shasum -a 256 "$1" | cut -d' ' -f1; }
elif command -v sha256sum >/dev/null 2>&1; then sha256() { sha256sum "$1" | cut -d' ' -f1; }
else say "需要 shasum 或 sha256sum 校验下载"; exit 1; fi

if [[ ${#dirs[@]} -eq 0 ]]; then
  [[ -d "$HOME/.claude" ]] && dirs+=("$HOME/.claude/skills")
  [[ -d "$HOME/.codex" ]] && dirs+=("$HOME/.codex/skills")
  dirs+=("$HOME/.agents/skills")
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fetch() { # url-path (after github.com) -> file; tries each mirror
  local url="https://github.com/$1" out="$2" mirror
  for mirror in "${MIRRORS[@]}"; do
    if curl -fsSL --connect-timeout 15 --max-time 300 --retry 2 -o "$out" "${mirror}${url}"; then
      return 0
    fi
    say "下载失败，换下一个来源：${mirror:-github.com}"
  done
  return 1
}

if [[ -n "$source_repo" ]]; then
  need go "从源码打包需要 Go（只在打包时需要）"
  say "从源码打包：$source_repo"
  (cd "$source_repo" && python3 scripts/build_skill.py --output "$work/build" >&2)
  package="$work/build/$NAME.skill"
else
  need curl "用于下载 skill 包"
  api="https://api.github.com/repos/$REPO/releases?per_page=30"
  [[ -n "$version" ]] && api="https://api.github.com/repos/$REPO/releases/tags/$version"
  curl -fsSL --connect-timeout 15 --max-time 60 "$api" -o "$work/releases.json" || {
    say "无法访问 GitHub API（$api）。可用 --version <tag> 重试，或 git clone 后用 --from-source <仓库目录>。"
    exit 1
  }
  read -r tag asset < <(python3 - "$work/releases.json" <<'PY'
import json, re, sys
data = json.load(open(sys.argv[1]))
for release in (data if isinstance(data, list) else [data]):
    for asset in release.get('assets', []):
        if re.fullmatch(r'rallycut-skill-.+\.skill', asset['name']):
            print(release['tag_name'], asset['name']); sys.exit(0)
sys.exit(1)
PY
  ) || {
    say "还没有包含 rallycut skill 的 Release。请 git clone https://github.com/$REPO 后运行："
    say "  bash scripts/install-skill.sh --from-source <仓库目录>    （需要 Go）"
    exit 1
  }
  say "下载 ${asset}（Release $tag）"
  package="$work/$asset"
  fetch "$REPO/releases/download/$tag/$asset" "$package" || { say "skill 包下载失败"; exit 1; }
  if fetch "$REPO/releases/download/$tag/SHA256SUMS-macos.txt" "$work/sums.txt"; then
    want="$(awk -v n="$asset" '$2==n {print $1}' "$work/sums.txt")"
    [[ -n "$want" ]] || { say "校验清单里没有 ${asset}，拒绝安装"; exit 1; }
    [[ "$(sha256 "$package")" == "$want" ]] || { say "SHA-256 不匹配，拒绝安装"; exit 1; }
  else
    say "无法下载 SHA256SUMS-macos.txt，拒绝安装未校验的包"; exit 1
  fi
fi

mkdir -p "$work/unpacked"
unzip -q "$package" -d "$work/unpacked"
skill="$work/unpacked/$NAME"
[[ -f "$skill/SKILL.md" && -f "$skill/assets/runtime/runtime-manifest.json" ]] || { say "包内容不完整，拒绝安装"; exit 1; }
chmod +x "$skill"/assets/bin/*/rallycut-cli* 2>/dev/null || true

installed=()
for root in "${dirs[@]}"; do
  mkdir -p "$root"
  target="$root/$NAME"
  stage="$(mktemp -d "$root/.rallycut-install-XXXXXX")"
  cp -R "$skill" "$stage/$NAME"
  if [[ -e "$target" ]]; then
    # Replace only a previous rallycut skill, never an unrelated folder.
    grep -q '^name: rallycut$' "$target/SKILL.md" 2>/dev/null || { rm -rf "$stage"; say "跳过 ${target}：已存在且不是 rallycut skill"; continue; }
    rm -rf "$target"
  fi
  mv "$stage/$NAME" "$target"
  rmdir "$stage"
  say "已安装：$target"
  installed+=("$target")
  if [[ -d "$root/rallycut-video-json" ]]; then
    say "  提示：$root/rallycut-video-json 是改名前的旧版本，确认不用后可删除，避免 agent 看到两个同类 skill"
  fi
done

# Smoke test of the installed launcher; plan / export / brief need only FFmpeg.
[[ ${#installed[@]} -gt 0 ]] || { say "没有安装到任何目录"; exit 1; }
first="${installed[0]}/scripts/rallycut.py"
python3 "$first" plan --help >/dev/null 2>&1 && say "自检通过：rallycut-cli 可运行" || say "自检未通过：请运行 python3 '$first' plan --help 查看原因"
command -v ffmpeg >/dev/null 2>&1 || say "提示：还需要安装 FFmpeg（macOS：brew install ffmpeg）"
say "完成。分析新视频前，agent 会征得你同意后运行 setup --download-model（需要 uv）。"
