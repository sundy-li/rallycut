# Build a Windows desktop EXE using the standard Wails resource pipeline.
# A clean checkout has no frontend/dist/index.html. Always build it first;
# never embed stale local assets or assume a plain Go build adds PE resources.
# This builds an EXE, not a portable runtime/installer. For a full distribution
# use the Windows preview workflow or `just package-windows`.
param(
    [string]$Go = "",
    [string]$Wails = "",
    [string]$Out = "build\bin\RallyCut.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$originalPath = $env:PATH
try {
    if ($env:OS -ne 'Windows_NT') { throw '请在 Windows 上运行此构建脚本。' }
    if (-not $Go) {
        $command = Get-Command go -ErrorAction SilentlyContinue
        if ($command) { $Go = $command.Source }
    }
    if (-not $Go -or -not (Test-Path $Go)) {
        throw '未找到 go。请安装 Go 1.25+，或用 -Go C:\path\to\go.exe 指定。'
    }
    # Wails' binding generator also invokes Go. Respect -Go for the whole
    # build process without changing the caller's persistent PATH.
    $env:PATH = "$(Split-Path -Parent ([IO.Path]::GetFullPath($Go)));$env:PATH"
    if (-not $Wails) {
        $command = Get-Command wails -ErrorAction SilentlyContinue
        if ($command) { $Wails = $command.Source }
    }
    if (-not $Wails -or -not (Test-Path $Wails)) {
        throw '未找到 Wails CLI。请执行 go install github.com/wailsapp/wails/v2/cmd/wails@v2.16.0。'
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw '未找到 npm，请安装 Node.js 22。' }
    if (-not [IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $root $Out }
    $destination = [IO.Path]::GetFullPath($Out)
    $filename = [IO.Path]::GetFileName($destination)
    if ([IO.Path]::GetExtension($filename) -ne '.exe') { throw '-Out 必须是 .exe 文件。' }

    # npm ci uses the committed lockfile. Wails then runs the configured fresh
    # frontend build and generates the application manifest, icons and VERSIONINFO.
    & npm --prefix frontend ci
    if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败，未构建 EXE。' }
    # Stamp version / commit for the in-app build label (backend/buildinfo).
    $version = $env:VERSION
    if (-not $version) { $version = (& git describe --tags --match 'v[0-9]*' --abbrev=0 2>$null) }
    if (-not $version) { $version = '0.1.0' }
    $version = $version.TrimStart('v')
    $commit = (& git rev-parse --short=12 HEAD 2>$null)
    $dirty = 'false'
    if ($commit -and (& git status --porcelain --untracked-files=no 2>$null)) { $dirty = 'true' }
    $built = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $pkg = 'rallycut/backend/buildinfo'
    $ldflags = "-X $pkg.Version=$version -X $pkg.Commit=$commit -X $pkg.Dirty=$dirty -X $pkg.BuildTime=$built"
    & $Wails build -platform windows/amd64 -compiler $Go -m -nosyncgomod -trimpath -ldflags $ldflags -o $filename
    if ($LASTEXITCODE -ne 0) { throw "Wails 构建失败：exit $LASTEXITCODE" }
    if (-not (Test-Path 'frontend/dist/index.html') -or
        -not (Get-ChildItem 'frontend/dist/assets' -Filter '*.js' -ErrorAction SilentlyContinue)) {
        throw '缺少新构建的前端首页或 JavaScript，拒绝输出不完整 EXE。'
    }
    $built = Join-Path $root "build\bin\$filename"
    if (-not (Test-Path $built)) { throw 'Wails 未生成预期的 EXE。' }
    if ([IO.Path]::GetFullPath($built) -ne $destination) {
        $parent = Split-Path -Parent $destination
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
        Copy-Item -LiteralPath $built -Destination $destination -Force
    }
    Get-Item -LiteralPath $destination | Select-Object FullName, Length, LastWriteTime
}
finally { $env:PATH = $originalPath; Pop-Location }
