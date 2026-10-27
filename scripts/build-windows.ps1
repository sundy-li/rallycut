# Build the Windows desktop binary from this checkout.
#
# `wails build` also runs the frontend toolchain. That is unnecessary here:
# frontend/dist is committed and embedded through //go:embed, so a plain Go
# build with the same tags Wails uses produces the same desktop binary.
# Wails v2 on Windows needs no cgo/gcc.
#
# The runtime environment is not embedded by a local build. The binary resolves
# <exe>/runtimes/<backend/runtimeenv/bundled-id.txt>, so either run the generated
# installer or point that file at an installed runtime id before building.
param(
    [string]$Go = "",
    [string]$Out = "build\bin\RallyCut.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not $Go) {
        $command = Get-Command go -ErrorAction SilentlyContinue
        if ($command) { $Go = $command.Source }
    }
    if (-not $Go -or -not (Test-Path $Go)) {
        throw "未找到 go。请安装 Go 1.25+，或用 -Go C:\path\to\go.exe 指定。"
    }

    $parent = Split-Path -Parent $Out
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }

    & $Go build -tags desktop,production -trimpath `
        -ldflags "-w -s -H windowsgui" -o $Out .
    if ($LASTEXITCODE -ne 0) { throw "go build 失败：exit $LASTEXITCODE" }

    Get-Item $Out | Select-Object FullName, Length, LastWriteTime
}
finally {
    Pop-Location
}
