#Requires -Version 5.1
<#
.SYNOPSIS
    AutoEdit-Lite — All-In-One Windows Installer

.DESCRIPTION
    Installs every prerequisite in a single double-click:
      1. Python 3.11  (auto-installed via winget if missing)
      2. FFmpeg       (auto-installed via winget if missing)
      3. Premiere Pro CEP plugin + registry debug key
      4. Python virtual environment + all pip dependencies
      5. CUDA / ctranslate2 compatibility fix for CPU-only machines
      6. settings.json so the plugin finds the Python backend
      7. Anthropic API key saved to .env
      8. Final verification that every package loads correctly

    Safe to re-run: each step is idempotent.

.NOTES
    Launch via install_all_windows.bat — do not run this .ps1 directly.
#>

param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Paths ──────────────────────────────────────────────────────────────────────
$scriptDir    = $PSScriptRoot
$pluginSrc    = Join-Path $scriptDir "premiere-plugin\com.autoedit.premiere"
$cepBase      = Join-Path $env:APPDATA "Adobe\CEP\extensions"
$pluginDst    = Join-Path $cepBase "com.autoedit.premiere"
$settingsDir  = Join-Path $env:APPDATA "AutoEdit"
$settingsFile = Join-Path $settingsDir "settings.json"
$venvDir      = Join-Path $scriptDir "venv"
$venvPython   = Join-Path $venvDir "Scripts\python.exe"
$envFile      = Join-Path $scriptDir ".env"
$envExample   = Join-Path $scriptDir ".env.example"
$reqFile      = Join-Path $scriptDir "requirements.txt"

$csxsVersions = @("9", "10", "11", "12")

# ── Helpers ────────────────────────────────────────────────────────────────────
function Write-Step { param([string]$msg) Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  [OK]    $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  [WARN]  $msg" -ForegroundColor Yellow }
function Write-Fail {
    param([string]$msg)
    Write-Host "`n  [ERROR] $msg`n" -ForegroundColor Red
    exit 1
}

# Reload PATH from registry so that winget-installed programs are found in
# the current session without needing a restart.
function Update-SessionPath {
    $machine = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $user    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($machine -and $user) { $env:PATH = "$machine;$user" }
    elseif ($machine)        { $env:PATH = $machine }
    elseif ($user)           { $env:PATH = $user }
}

# ── Banner ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor White
Write-Host "   AutoEdit-Lite — All-In-One Windows Installer" -ForegroundColor White
Write-Host "  ============================================================" -ForegroundColor White
Write-Host "  This script will install everything automatically." -ForegroundColor Gray
Write-Host "  It is safe to run more than once." -ForegroundColor Gray
Write-Host ""

# ── Step 0: Check VC++ runtime (CTranslate2 needs MSVC 2015-2022) ─────────────
# faster-whisper -> ctranslate2 links the MSVC C++ runtime. Fresh Windows
# installs lack it and the Python import will fail with an opaque "DLL load
# failed" message — install_all_windows.ps1 previously did NOT check for this.
function Test-VCRedistInstalled {
    $key = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
    try {
        $val = Get-ItemProperty -Path $key -Name Installed -ErrorAction Stop
        return [int]$val.Installed -eq 1
    } catch {
        return $false
    }
}

Write-Step "Step 0/9 — Checking Visual C++ runtime (required by faster-whisper)..."
if (Test-VCRedistInstalled) {
    Write-OK "Visual C++ 2015-2022 redistributable is installed."
} else {
    Write-Warn "Visual C++ redistributable is missing. Installing via winget..."
    try {
        winget install --id Microsoft.VCRedist.2015+.x64 `
            --accept-source-agreements `
            --accept-package-agreements `
            --silent
    } catch {
        Write-Warn "winget install of VCRedist failed: $($_.Exception.Message)"
    }
    if (-not (Test-VCRedistInstalled)) {
        Write-Warn "VC++ redistributable still not detected. faster-whisper may fail to import."
        Write-Host "  Manual download: https://aka.ms/vs/17/release/vc_redist.x64.exe" -ForegroundColor Yellow
    } else {
        Write-OK "Visual C++ redistributable installed."
    }
}

# ── Step 1: Check winget availability ─────────────────────────────────────────
Write-Step "Step 1/9 — Checking Windows Package Manager (winget)..."

$wingetAvailable = $false
try {
    $null = winget --version 2>&1
    if ($LASTEXITCODE -eq 0) { $wingetAvailable = $true }
} catch {}

if ($wingetAvailable) {
    Write-OK "winget is available."
} else {
    Write-Warn "winget is not available on this machine."
    Write-Host "  winget is built into Windows 10 (version 1809+) and Windows 11." -ForegroundColor Yellow
    Write-Host "  If missing, install 'App Installer' from the Microsoft Store:" -ForegroundColor Yellow
    Write-Host "    https://aka.ms/getwinget" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  You can still continue, but Python and FFmpeg must be installed manually." -ForegroundColor Yellow
}

# ── Step 2: Python ─────────────────────────────────────────────────────────────
Write-Step "Step 2/9 — Checking Python..."

$pythonCmd = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $out = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$out" -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 9)) {
                $pythonCmd = $candidate
                Write-OK "$out detected."
                break
            } else {
                Write-Warn "Found $out but 3.9+ is required."
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    if ($wingetAvailable) {
        Write-Host "  Python not found. Installing Python 3.11 via winget..." -ForegroundColor Gray
        winget install --id Python.Python.3.11 `
            --scope machine `
            --accept-source-agreements `
            --accept-package-agreements `
            --silent

        if ($LASTEXITCODE -ne 0) {
            # Some machines need user scope if machine scope is denied
            Write-Warn "Machine-scope install failed. Retrying with user scope..."
            winget install --id Python.Python.3.11 `
                --accept-source-agreements `
                --accept-package-agreements `
                --silent
        }

        Update-SessionPath

        # Re-check after install
        foreach ($candidate in @("python", "python3", "py")) {
            try {
                $out = & $candidate --version 2>&1
                if ($LASTEXITCODE -eq 0 -and "$out" -match "Python") {
                    $pythonCmd = $candidate
                    Write-OK "Python installed successfully: $out"
                    break
                }
            } catch {}
        }

        if (-not $pythonCmd) {
            Write-Fail ("Python was installed but is not yet on PATH.`n" +
                        "  Please close this window, RESTART your computer, then" +
                        " double-click install_all_windows.bat again.")
        }
    } else {
        Write-Host ""
        Write-Host "  Python was not found on your PATH and winget is unavailable." -ForegroundColor Red
        Write-Host "  Install Python manually:" -ForegroundColor Yellow
        Write-Host "    1. Open: https://www.python.org/downloads/" -ForegroundColor Yellow
        Write-Host "    2. Download Python 3.11 or newer" -ForegroundColor Yellow
        Write-Host "    3. Run the installer and tick 'Add Python to PATH'" -ForegroundColor Yellow
        Write-Host "    4. Re-run this installer" -ForegroundColor Yellow
        Write-Host ""
        exit 1
    }
}

# ── Step 3: FFmpeg ─────────────────────────────────────────────────────────────
Write-Step "Step 3/9 — Checking FFmpeg..."

$ffmpegOk = $false
try {
    $null = ffmpeg -version 2>&1
    if ($LASTEXITCODE -eq 0) { $ffmpegOk = $true }
} catch {}

if ($ffmpegOk) {
    Write-OK "FFmpeg is already installed."
} elseif ($wingetAvailable) {
    Write-Host "  FFmpeg not found. Installing via winget..." -ForegroundColor Gray
    winget install --id Gyan.FFmpeg `
        --accept-source-agreements `
        --accept-package-agreements `
        --silent

    Update-SessionPath

    try {
        $null = ffmpeg -version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-OK "FFmpeg installed successfully."
        } else {
            Write-Warn ("FFmpeg was installed but PATH needs a refresh.`n" +
                        "  If FFmpeg errors appear when you run the tool, restart your" +
                        " PC and try again.")
        }
    } catch {
        Write-Warn "FFmpeg installed but not yet on PATH. Restart your PC if errors occur."
    }
} else {
    Write-Host ""
    Write-Host "  FFmpeg not found and winget is unavailable." -ForegroundColor Yellow
    Write-Host "  Install FFmpeg manually:" -ForegroundColor Yellow
    Write-Host "    1. Go to: https://github.com/BtbN/FFmpeg-Builds/releases" -ForegroundColor Yellow
    Write-Host "    2. Download: ffmpeg-master-latest-win64-gpl.zip" -ForegroundColor Yellow
    Write-Host "    3. Unzip and add the 'bin' folder to your PATH" -ForegroundColor Yellow
    Write-Host "    4. Re-run this installer" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# ── Step 4: Premiere Pro plugin ────────────────────────────────────────────────
Write-Step "Step 4/9 — Installing Premiere Pro plugin..."

if (-not (Test-Path $pluginSrc)) {
    Write-Warn "Premiere plugin folder not found at: $pluginSrc"
    Write-Warn "Skipping plugin installation. The standalone Python tool will still work."
} else {
    if (-not (Test-Path $cepBase)) {
        New-Item -ItemType Directory -Path $cepBase -Force | Out-Null
    }
    if (Test-Path $pluginDst) {
        Remove-Item -Path $pluginDst -Recurse -Force
    }
    Copy-Item -Path $pluginSrc -Destination $pluginDst -Recurse -Force
    Write-OK "Plugin installed to: $pluginDst"
}

# ── Step 5: CEP registry key ───────────────────────────────────────────────────
Write-Step "Step 5/9 — Setting Premiere Pro debug registry key..."

foreach ($ver in $csxsVersions) {
    $key = "HKCU:\SOFTWARE\Adobe\CSXS.$ver"
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name "PlayerDebugMode" -Value "1" -Type String
    Write-OK "CSXS.$ver\PlayerDebugMode = 1"
}

# ── Step 6: Python venv + dependencies ────────────────────────────────────────
Write-Step "Step 6/9 — Setting up Python virtual environment and dependencies..."

if (-not (Test-Path $reqFile)) {
    Write-Fail "requirements.txt not found at: $reqFile"
}

# Recreate venv for a clean install
if (Test-Path $venvDir) {
    Write-Host "  Existing venv found — recreating for a clean install..." -ForegroundColor Gray
    Remove-Item -Path $venvDir -Recurse -Force
}

Write-Host "  Creating virtual environment..." -ForegroundColor Gray
& $pythonCmd -m venv $venvDir
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create virtual environment." }
Write-OK "Virtual environment created."

Write-Host "  Upgrading pip..." -ForegroundColor Gray
& $venvPython -m pip install --quiet --upgrade pip

Write-Host "  Installing dependencies (this may take a few minutes)..." -ForegroundColor Gray
& $venvPython -m pip install --quiet -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Fail ("pip install failed.`n" +
                "  Check your internet connection and try again.`n" +
                "  If the error mentions a specific package, try running:`n" +
                "    $venvPython -m pip install -r $reqFile")
}
Write-OK "All Python packages installed."

# ── Step 7: CUDA / ctranslate2 compatibility ───────────────────────────────────
Write-Step "Step 7/9 — Checking GPU / CUDA compatibility..."

# Test whether faster-whisper loads on this machine (CPU mode)
$cudaTest = & $venvPython -c "import os; os.environ['CUDA_VISIBLE_DEVICES']='-1'; from faster_whisper import WhisperModel; print('ok')" 2>&1
if ($LASTEXITCODE -ne 0 -or "$cudaTest" -notmatch "ok") {
    Write-Warn "CUDA compatibility issue detected (cublas64_12.dll or similar)."
    Write-Host "  Installing CPU-compatible ctranslate2 build..." -ForegroundColor Gray
    & $venvPython -m pip install "ctranslate2>=3.20.0,<4.0.0" --force-reinstall --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail ("Could not fix the CUDA issue automatically.`n" +
                    "  Run manually: $venvPython -m pip install `"ctranslate2>=3.20.0,<4.0.0`" --force-reinstall")
    }
    Write-OK "ctranslate2 fixed — no CUDA required, CPU mode enabled."
} else {
    Write-OK "faster-whisper loads correctly on this machine."
}

# ── Step 8: settings.json + API key ───────────────────────────────────────────
Write-Step "Step 8/9 — Saving settings and API key..."

# Write %APPDATA%\AutoEdit\settings.json
if (-not (Test-Path $settingsDir)) {
    New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
}

$settings = [ordered]@{
    backendPath = $scriptDir
    pythonPath  = $venvPython
} | ConvertTo-Json -Compress

[System.IO.File]::WriteAllText($settingsFile, $settings, [System.Text.Encoding]::UTF8)
Write-OK "Settings written to: $settingsFile"

# API key — skip if .env already contains a real key
$existingKey = ""
if (Test-Path $envFile) {
    $envContent  = Get-Content $envFile -Raw
    if ($envContent -match "ANTHROPIC_API_KEY=([^\r\n]+)") {
        $existingKey = $Matches[1].Trim()
    }
}

if ($existingKey -and $existingKey -ne "your_key_here" -and $existingKey.StartsWith("sk-ant")) {
    Write-OK "Existing API key found in .env — keeping it."
} else {
    # Create .env from example if needed
    if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
        Copy-Item -Path $envExample -Destination $envFile
    }

    Write-Host ""
    Write-Host "  ----------------------------------------------------------------" -ForegroundColor White
    Write-Host "  Enter your Anthropic API key (starts with sk-ant-)." -ForegroundColor White
    Write-Host "  Get one free at: https://console.anthropic.com/" -ForegroundColor Gray
    Write-Host "  ----------------------------------------------------------------" -ForegroundColor White
    $apiKey = Read-Host "  API key"
    $apiKey = $apiKey.Trim()

    if ($apiKey -and $apiKey.StartsWith("sk-ant")) {
        "ANTHROPIC_API_KEY=$apiKey" | Out-File -FilePath $envFile -Encoding UTF8 -Force
        Write-OK "API key saved to .env"
    } elseif ($apiKey) {
        Write-Warn "The key you entered doesn't look like an Anthropic key (should start with sk-ant-)."
        Write-Warn "Saved anyway. Edit .env manually if the tool gives authentication errors."
        "ANTHROPIC_API_KEY=$apiKey" | Out-File -FilePath $envFile -Encoding UTF8 -Force
    } else {
        Write-Warn "No API key entered. Add it manually to .env:"
        Write-Warn "  ANTHROPIC_API_KEY=sk-ant-..."
    }
}

# ── Step 9: Final verification (matches launcher self-check) ──────────────────
Write-Step "Step 9/9 — Verifying every dependency the launcher will need..."

# Mirror the same import set the bundled-installer launcher checks at startup,
# so source-build users get the same pre-flight signal.
$verifyScript = @"
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
import faster_whisper, ctranslate2, anthropic, ffmpeg, dotenv, opentimelineio
print('ALL_OK')
"@

$verifyOut = & $venvPython -c $verifyScript 2>&1
if ("$verifyOut" -match "ALL_OK") {
    Write-OK "All packages verified successfully."
} else {
    Write-Warn "Verification failed:"
    Write-Host $verifyOut -ForegroundColor Red
    Write-Warn "If the error mentions 'DLL load failed' for ctranslate2, the VC++"
    Write-Warn "redistributable installation in Step 0 may have failed silently."
    Write-Warn "Install manually from: https://aka.ms/vs/17/release/vc_redist.x64.exe"
}

# ── Done ───────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "   AutoEdit-Lite installed successfully!" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host "   1. Restart Adobe Premiere Pro (close and reopen it)" -ForegroundColor White
Write-Host "   2. In Premiere Pro: Window -> Extensions -> AutoEdit" -ForegroundColor White
Write-Host "   3. The panel will open — no further setup needed." -ForegroundColor White
Write-Host ""
Write-Host "  To run the standalone tool (no Premiere):" -ForegroundColor Gray
Write-Host "   Double-click  run_windows.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "  To uninstall, run:  install_windows.bat --uninstall" -ForegroundColor Gray
Write-Host ""
