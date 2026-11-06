[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$NoInstall
)

$ErrorActionPreference = "Stop"

if ($env:OS -ne "Windows_NT") {
    throw "This packaging script must run on Windows."
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DistRoot = Join-Path $Root "dist"
$BuildRoot = Join-Path $Root "build\pyinstaller"
$WorkPath = Join-Path $BuildRoot "work"
$SpecPath = Join-Path $BuildRoot "spec"
$PluginSource = Join-Path $Root "plugins"
$ReadmeSource = Join-Path $Root "README.md"
$LicenseSource = Join-Path $Root "LICENSE"

Push-Location $Root
try {
    & $Python -c "import sys; raise SystemExit(0 if sys.platform == 'win32' and sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11+ for Windows is required. Selected interpreter: $Python"
    }

    if (-not $NoInstall) {
        & $Python -m pip install -e ".[build]"
        if ($LASTEXITCODE -ne 0) {
            throw "Installing project and build dependencies failed."
        }
    }

    New-Item -ItemType Directory -Force -Path $WorkPath, $SpecPath | Out-Null
    $PyInstallerArgs = @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name", "BILEWorkbench",
        "--paths", "src",
        "--collect-submodules", "bile_workbench",
        "--collect-all", "PIL",
        "--add-data", "${PluginSource};plugins",
        "--add-data", "${ReadmeSource};.",
        "--add-data", "${LicenseSource};.",
        "--distpath", $DistRoot,
        "--workpath", $WorkPath,
        "--specpath", $SpecPath,
        "packaging/launcher.py"
    )

    & $Python @PyInstallerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $BundleRoot = Join-Path $DistRoot "BILEWorkbench"
    $Executable = Join-Path $BundleRoot "BILEWorkbench.exe"
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Expected executable was not created: $Executable"
    }

    $PluginRoot = Join-Path $BundleRoot "_internal\plugins"
    if (-not (Test-Path -LiteralPath $PluginRoot -PathType Container)) {
        $PluginRoot = Join-Path $BundleRoot "plugins"
    }

    foreach ($PluginId in @("anime-claude-girl", "anime-openai-girl")) {
        $PluginDir = Join-Path $PluginRoot $PluginId
        $ThemeDir = Join-Path $PluginDir "themes"
        foreach ($RequiredFile in @(
            (Join-Path $PluginDir "plugin.json"),
            (Join-Path $ThemeDir "light.qss"),
            (Join-Path $ThemeDir "dark.qss")
        )) {
            if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
                throw "Bundled theme resource is missing: $RequiredFile"
            }
        }
    }

    Write-Host "BILE Workbench Windows bundle created:"
    Write-Host "  $Executable"
    Write-Host "  Plugins: $PluginRoot"
}
finally {
    Pop-Location
}
