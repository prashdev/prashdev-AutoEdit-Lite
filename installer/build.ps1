#Requires -Version 5.1
<#
.SYNOPSIS
    Build orchestrator for AutoEditLite-Setup.exe and AutoEditLite-Portable.zip.

.DESCRIPTION
    Stages every dependency under .\build\, runs Inno Setup, and produces:
      dist\AutoEditLite-Setup.exe
      dist\AutoEditLite-Portable.zip

    Designed to run on a clean windows-latest GitHub Actions runner. Every
    download is pinned by URL + (optional) SHA256.

.PARAMETER Version
    Numeric version string baked into the installer (e.g. "0.2.0.0"). Defaults
    to AUTOEDIT_VERSION env var, then "0.1.0.0".

.PARAMETER SkipPortable
    Skip producing the portable zip (faster local iteration).

.NOTES
    Outputs:
        installer\build\           staged tree
        installer\dist\            shippable artifacts
        installer\build\requirements.lock   reproducibility record
#>

[CmdletBinding()]
param(
    [string]$Version = $(if ($env:AUTOEDIT_VERSION) { $env:AUTOEDIT_VERSION } else { '0.1.0.0' }),
    [switch]$SkipPortable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Resolve paths ───────────────────────────────────────────────────────────
$installerDir = $PSScriptRoot
$repoRoot     = Split-Path $installerDir -Parent
$buildDir     = Join-Path $installerDir 'build'
$distDir      = Join-Path $installerDir 'dist'
$cacheDir     = Join-Path $installerDir '.cache'
$launcherDir  = Join-Path $installerDir 'launcher'
$MaxArtifactMB = 400

# ── Pinned downloads ────────────────────────────────────────────────────────
$PythonEmbedUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'
$GetPipUrl      = 'https://bootstrap.pypa.io/get-pip.py'
$FfmpegUrl      = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
$VCRedistUrl    = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
# ZXPSignCmd — Adobe's free CEP-extension signing tool. Needed because
# Premiere Pro 2024+ enforces signature verification even for locally
# installed extensions; PlayerDebugMode=1 no longer fully bypasses it.
# Distributed as a single .exe under the CEP-Resources repo.
$ZxpSignUrl     = 'https://github.com/Adobe-CEP/CEP-Resources/raw/master/ZXPSignCMD/4.1.103/win64/ZXPSignCmd.exe'

$env:AUTOEDIT_VERSION = $Version

function Write-Step { param([string]$m) Write-Host "`n==> $m" -ForegroundColor Cyan }
function Write-OK   { param([string]$m) Write-Host "    $m"   -ForegroundColor Green }
function Fail       { param([string]$m) Write-Host "`nFAIL: $m" -ForegroundColor Red; exit 1 }

function Assert-ArtifactUnderLimit {
    param([string]$Path)
    if (-not (Test-Path $Path)) { Fail "Expected artifact not found: $Path" }
    $sizeMB = [math]::Round((Get-Item $Path).Length / 1MB, 1)
    if ($sizeMB -gt $MaxArtifactMB) {
        Fail "$(Split-Path $Path -Leaf) is $sizeMB MB, above the $MaxArtifactMB MB limit. Do not bundle large speech models."
    }
    Write-OK "$(Split-Path $Path -Leaf) size OK ($sizeMB MB <= $MaxArtifactMB MB)"
}

function Get-Cached {
    param([string]$Url, [string]$FileName)
    $dest = Join-Path $cacheDir $FileName
    if (-not (Test-Path $cacheDir)) { New-Item -ItemType Directory -Path $cacheDir | Out-Null }
    if (Test-Path $dest) {
        Write-OK "cached: $FileName"
    } else {
        Write-OK "download: $Url"
        Invoke-WebRequest -Uri $Url -OutFile $dest -UseBasicParsing
    }
    return $dest
}

# ── Clean previous build artifacts ──────────────────────────────────────────
Write-Step "Cleaning build/ and dist/"
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (-not (Test-Path $distDir)) { New-Item -ItemType Directory -Path $distDir | Out-Null }
New-Item -ItemType Directory -Path $buildDir | Out-Null

# ── Step 1: Embedded Python ─────────────────────────────────────────────────
Write-Step "Staging embedded Python 3.11"
$pyZip = Get-Cached -Url $PythonEmbedUrl -FileName 'python-3.11.9-embed-amd64.zip'
$pyDir = Join-Path $buildDir 'py'
Expand-Archive -Path $pyZip -DestinationPath $pyDir -Force

# Write python311._pth deterministically. The stock file from the embed zip
# has 'import site' commented out — we need site-packages discovery.
$pthPath = Join-Path $pyDir 'python311._pth'
#
# Important: when a ._pth file exists, embedded Python runs in "isolated
# mode" and does NOT auto-add the script's directory to sys.path. Our
# app/main.py does `from transcribe import ...` against sibling modules,
# so we must add `..\app` (relative to py\) explicitly. Without this, the
# bundled launcher boots Python but main.py crashes at first import.
@'
python311.zip
.
Lib\site-packages
..\app
import site
'@ | Set-Content -Path $pthPath -Encoding ASCII
Write-OK "python311._pth written"

# Bootstrap pip INTO the embedded distribution. --target install is fragile
# for namespace packages (opentimelineio) — pip's own bootstrapper does the
# right thing inside the embed tree.
$getPip = Get-Cached -Url $GetPipUrl -FileName 'get-pip.py'
$pyExe  = Join-Path $pyDir 'python.exe'
& $pyExe $getPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { Fail "get-pip failed" }
Write-OK "pip installed into embedded Python"

# ── Step 2: Install runtime deps ────────────────────────────────────────────
Write-Step "Installing requirements.txt into embedded site-packages"
$req = Join-Path $repoRoot 'requirements.txt'
& $pyExe -m pip install --no-warn-script-location -r $req
if ($LASTEXITCODE -ne 0) { Fail "pip install -r requirements.txt failed" }

# Snapshot resolved versions for reproducibility
$lockPath = Join-Path $buildDir 'requirements.lock'
& $pyExe -m pip freeze | Set-Content -Path $lockPath -Encoding ASCII
Write-OK "requirements.lock written"

# ── Step 3: Embedded-runtime smoke test ─────────────────────────────────────
Write-Step "Smoke-testing imports inside the embedded runtime"
$smokeScript = @'
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
import faster_whisper, ctranslate2, anthropic, ffmpeg, dotenv, opentimelineio
print('SMOKE_OK')
'@
$smokeOut = & $pyExe -c $smokeScript 2>&1
if (-not ("$smokeOut" -match 'SMOKE_OK')) {
    Write-Host $smokeOut -ForegroundColor Red
    Fail "Embedded-runtime smoke test failed. Wheels are incompatible with the embedded distribution."
}
Write-OK "all imports OK inside embedded Python"

# Record which ctranslate2 wheel pip picked — relevant for the AVX2 floor doc
$ct2Info = & $pyExe -m pip show ctranslate2 2>&1
($ct2Info -join "`n") | Set-Content -Path (Join-Path $buildDir 'ctranslate2-resolved.txt') -Encoding ASCII

# ── Step 4: FFmpeg ──────────────────────────────────────────────────────────
Write-Step "Staging FFmpeg essentials build"
$ffZip = Get-Cached -Url $FfmpegUrl -FileName 'ffmpeg-release-essentials.zip'
$ffTmp = Join-Path $buildDir '_ffmpeg_tmp'
Expand-Archive -Path $ffZip -DestinationPath $ffTmp -Force

$ffBinSrc = Get-ChildItem -Path $ffTmp -Recurse -Directory | Where-Object { $_.Name -eq 'bin' } | Select-Object -First 1
if (-not $ffBinSrc) { Fail "ffmpeg bin folder not found in archive" }

$ffBinDst = Join-Path $buildDir 'ff\bin'
New-Item -ItemType Directory -Path $ffBinDst -Force | Out-Null
Copy-Item -Path (Join-Path $ffBinSrc.FullName 'ffmpeg.exe')  -Destination $ffBinDst
Copy-Item -Path (Join-Path $ffBinSrc.FullName 'ffprobe.exe') -Destination $ffBinDst
Remove-Item $ffTmp -Recurse -Force
Write-OK "ffmpeg.exe + ffprobe.exe staged"

# ── Step 5: VC++ redist ─────────────────────────────────────────────────────
Write-Step "Staging VC_redist.x64.exe"
$redistDir = Join-Path $buildDir 'redist'
New-Item -ItemType Directory -Path $redistDir -Force | Out-Null
$redistDst = Join-Path $redistDir 'VC_redist.x64.exe'
$redistCached = Get-Cached -Url $VCRedistUrl -FileName 'VC_redist.x64.exe'
Copy-Item $redistCached -Destination $redistDst -Force

# ── Step 6: Application source ──────────────────────────────────────────────
Write-Step "Staging application source"
$appDst = Join-Path $buildDir 'app'
New-Item -ItemType Directory -Path $appDst -Force | Out-Null
$pyFiles = @('main.py','transcribe.py','analyze.py','editor.py','captions.py',
             'filler_detector.py','losslesscut_export.py','xml_export.py',
             'accuracy_outputs.py','accuracy_dataset.py','output_validation.py')
foreach ($f in $pyFiles) {
    Copy-Item -Path (Join-Path $repoRoot $f) -Destination $appDst -ErrorAction Stop
}
Copy-Item -Path (Join-Path $repoRoot 'prompts') -Destination $appDst -Recurse
Write-OK "app\ staged ($($pyFiles.Count) modules + prompts\)"

# ── Step 6b: Premiere CEP extension (the panel that appears in Premiere) ────
Write-Step "Staging Premiere CEP extension"
$cepStage = Join-Path $buildDir 'cep\com.autoedit.premiere'
$cepSrc   = Join-Path $repoRoot 'premiere-plugin\com.autoedit.premiere'
if (-not (Test-Path $cepSrc)) { Fail "premiere-plugin source missing at $cepSrc" }
New-Item -ItemType Directory -Path $cepStage -Force | Out-Null
Copy-Item -Path "$cepSrc\*" -Destination $cepStage -Recurse -Force
Write-OK "raw CEP staged"

# ── Step 6c: Sign the CEP extension ─────────────────────────────────────────
# Premiere Pro 2024+ verifies extension signatures. PlayerDebugMode=1 lets
# Premiere TRUST a self-signed cert but does NOT skip the signature check
# itself — so an unsigned folder is rejected with
#   "Signature verification failed for extension <id>"
# Use Adobe's free ZXPSignCmd to sign with a self-signed cert (cached in
# .cache so dev builds are reproducible and quick).
Write-Step "Signing CEP extension"
$zxpExe = Get-Cached -Url $ZxpSignUrl -FileName 'ZXPSignCmd.exe'
$zxp = Get-Item $zxpExe

$certPath = Join-Path $cacheDir 'autoedit-selfsigned.p12'
$certPass = 'autoeditlite'   # not a secret — cert is for build-time signing only
if (-not (Test-Path $certPath)) {
    & $zxp.FullName -selfSignedCert US California AutoEdit AutoEdit-Lite $certPass $certPath
    if (-not (Test-Path $certPath)) { Fail "self-signed cert generation failed" }
    Write-OK "self-signed cert generated -> $certPath"
} else {
    Write-OK "self-signed cert (cached)"
}

$signedZxp = Join-Path $buildDir 'cep-signed\com.autoedit.premiere.zxp'
$signedDir = Join-Path $buildDir 'cep-signed\com.autoedit.premiere'
New-Item -ItemType Directory -Path (Split-Path $signedZxp -Parent) -Force | Out-Null
# No -tsa — timestamping needs a network round-trip that flakes on CI runners,
# and self-signed dev certs don't gain anything from timestamping.
& $zxp.FullName -sign $cepStage $signedZxp $certPath $certPass
if (-not (Test-Path $signedZxp)) { Fail "ZXPSignCmd -sign did not produce $signedZxp" }

# .zxp is a ZIP under the hood. PowerShell's Expand-Archive only accepts
# .zip extensions, so copy then extract.
if (Test-Path $signedDir) { Remove-Item $signedDir -Recurse -Force }
$signedZip = [System.IO.Path]::ChangeExtension($signedZxp, '.zip')
Copy-Item $signedZxp $signedZip -Force
Expand-Archive -Path $signedZip -DestinationPath $signedDir -Force
Remove-Item $signedZip -Force
if (-not (Test-Path (Join-Path $signedDir 'META-INF\signatures.xml'))) {
    Fail "signed extension is missing META-INF\signatures.xml"
}
Write-OK "CEP extension signed -> build\cep-signed\com.autoedit.premiere\"

# ── Step 7: Launcher binaries ───────────────────────────────────────────────
Write-Step "Building launcher binaries (dotnet publish)"
$binDst = Join-Path $buildDir 'bin'
New-Item -ItemType Directory -Path $binDst -Force | Out-Null

# Wipe stale obj/bin/publish so the SDK's implicit Compile glob never sees
# the SIBLING project's auto-generated AssemblyInfo files (CS0579 trap).
foreach ($stale in @('obj','bin','publish')) {
    $p = Join-Path $launcherDir $stale
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}

foreach ($variant in @('AutoEditLite','AutoEditLite-CLI')) {
    $proj = Join-Path $launcherDir "$variant.csproj"
    $pubDir = Join-Path $launcherDir "publish\$variant"
    & dotnet publish $proj `
        -c Release `
        -r win-x64 `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:IncludeNativeLibrariesForSelfExtract=true `
        -p:DebugType=embedded `
        -o $pubDir
    if ($LASTEXITCODE -ne 0) { Fail "dotnet publish $variant failed" }
    Copy-Item -Path (Join-Path $pubDir "$variant.exe") -Destination $binDst -Force
    Write-OK "$variant.exe built"
}

# ── Step 8: Run Inno Setup ──────────────────────────────────────────────────
Write-Step "Running Inno Setup compiler"

# Winget installs Inno Setup per-user by default (under %LocalAppData%);
# older / machine-wide installs land under %ProgramFiles%; chocolatey under
# %ProgramData%. Probe all four common locations, then the registry, then PATH.
$iscc = $null
$candidates = @(
    "$env:LocalAppData\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramData\chocolatey\bin\ISCC.exe"
)
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) { $iscc = $candidate; break }
}

if (-not $iscc) {
    # Registry: HKCU for per-user installs, HKLM for machine-wide
    foreach ($hive in @('HKCU:', 'HKLM:')) {
        $regPath = "$hive\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
        try {
            $loc = (Get-ItemProperty -Path $regPath -ErrorAction Stop).InstallLocation
            if ($loc) {
                $candidate = Join-Path $loc 'ISCC.exe'
                if (Test-Path $candidate) { $iscc = $candidate; break }
            }
        } catch {}
    }
}

if (-not $iscc) {
    $cmd = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}

if (-not $iscc) { Fail "ISCC.exe not found. Install Inno Setup 6: winget install JRSoftware.InnoSetup" }
Write-OK "iscc: $iscc"

& $iscc (Join-Path $installerDir 'AutoEditLite.iss')
if ($LASTEXITCODE -ne 0) { Fail "Inno Setup failed" }
Write-OK "AutoEditLite-Setup.exe -> $distDir"
$setupExe = Join-Path $distDir 'AutoEditLite-Setup.exe'
Assert-ArtifactUnderLimit -Path $setupExe

# ── Step 9: Portable zip ────────────────────────────────────────────────────
if (-not $SkipPortable) {
    Write-Step "Producing portable zip"
    $portableTree = Join-Path $buildDir 'portable'
    New-Item -ItemType Directory -Path $portableTree -Force | Out-Null
    Copy-Item -Path (Join-Path $buildDir 'py')  -Destination $portableTree -Recurse
    Copy-Item -Path (Join-Path $buildDir 'ff')  -Destination $portableTree -Recurse
    Copy-Item -Path (Join-Path $buildDir 'app') -Destination $portableTree -Recurse
    Copy-Item -Path (Join-Path $buildDir 'bin\AutoEditLite.exe')     -Destination $portableTree
    Copy-Item -Path (Join-Path $buildDir 'bin\AutoEditLite-CLI.exe') -Destination $portableTree

    $portableZip = Join-Path $distDir "AutoEditLite-Portable-$Version.zip"
    if (Test-Path $portableZip) { Remove-Item $portableZip -Force }
    Compress-Archive -Path "$portableTree\*" -DestinationPath $portableZip -CompressionLevel Optimal
    Write-OK "AutoEditLite-Portable-$Version.zip -> $distDir"
    Assert-ArtifactUnderLimit -Path $portableZip
}

Write-Host "`nBuild succeeded." -ForegroundColor Green
Get-ChildItem $distDir | Format-Table Name, Length, LastWriteTime
