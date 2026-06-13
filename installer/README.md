# AutoEdit-Lite — Windows installer

Single-artifact Windows installer for AutoEdit-Lite. Produces:

- `dist\AutoEditLite-Setup.exe` — Inno Setup installer (recommended)
- `dist\AutoEditLite-Portable-<version>.zip` — extract-and-run, no admin

The installer bundles **everything** the app needs — embedded Python 3.11,
pre-resolved pip dependencies, FFmpeg, and the VC++ redistributable —
so a brand-new Windows install with no Python, no FFmpeg, no internet for
pip, and no admin rights still ends up with a working tool.

## Project Status

**Last updated: 2026-06-13**

- Latest installer build: **Succeeded**
- Estimated implementation progress: **95% complete; approximately 5%
  remaining**
- Measured progress toward 95% human-editor agreement: **Not yet measurable;
  representative human-labelled evaluation is still required**
- `dist\AutoEditLite-Setup.exe`: **234.75 MiB**
- `dist\AutoEditLite-Portable-0.2.0.zip`: **315.89 MiB**
- Both artifacts are below the **400 MiB** limit.
- Staged model-asset audit: **No Whisper or other large speech-model bundle;
  dependency assets include a 1.19 MiB Silero VAD model and tiny ONNX Runtime
  samples**
- Embedded CLI smoke test: **Passed**
- Staged shipped-source hashes: **Match repository source**
- Markdown status coverage: **Verified across every project Markdown file**
- Current work: **Collect, human-label, render, and evaluate at least 10
  complete actual representative cases for each target language**
- Current iteration steps: **Audit 100% | Markdown status 100% | Failing
  regression 100% | Implementation 100% | Verification/rebuild/docs 100%**

Read [`..\PROJECT_STATUS.md`](../PROJECT_STATUS.md) before rebuilding. After
every meaningful completed project step, update the authoritative ledger and
this section. When a build occurs, also refresh artifact sizes and audit
evidence.

## Layout

```
installer/
├── AutoEditLite.iss         # Inno Setup script (top-level)
├── preflight.iss            # Pascal [Code] helpers, included by AutoEditLite.iss
├── build.ps1                # Build orchestrator (run this)
├── launcher/
│   ├── Program.cs           # Shared launcher source
│   ├── AutoEditLite.csproj      # WinExe variant (no console)
│   ├── AutoEditLite-CLI.csproj  # Exe variant (console attached)
│   └── app.manifest         # asInvoker + longPathAware + UTF-8 ACP
├── icon.ico                 # Setup wizard icon (drop in here)
├── build/                   # Staged tree (generated)
├── dist/                    # Shippable artifacts (generated)
└── .cache/                  # Downloaded prerequisites (generated)
```

## Build prerequisites

| Tool | Why | How |
|---|---|---|
| **Inno Setup 6** | Compiles `AutoEditLite.iss` → `Setup.exe` | https://jrsoftware.org/isdl.php |
| **.NET 8 SDK** | Compiles the launcher binaries | `winget install Microsoft.DotNet.SDK.8` |
| **PowerShell 5.1+** | Runs `build.ps1` | Ships with Windows |

Drop a 256×256 `icon.ico` into `installer\` before building (optional, the
script falls back to no icon if missing — adjust `SetupIconFile=` in
`AutoEditLite.iss` if you remove the file).

## Build locally

```powershell
cd installer
.\build.ps1 -Version 0.2.0
```

First run downloads ~200 MB of prerequisites into `.cache\` and reuses them
on subsequent builds. Full build takes 3–5 minutes on a warm cache.

## What the installer does (end-user view)

1. Per-user install (no UAC) into `%LocalAppData%\Programs\AutoEditLite\`.
2. Asks for the Anthropic API key in a wizard page; writes it to
   `%APPDATA%\AutoEditLite\.env`.
3. Detects Premiere Pro via three independent signals and only writes
   `PlayerDebugMode` to `HKCU\Software\Adobe\CSXS.N` if Premiere is found.
   Surfaces the detected version on the install-complete page.
4. Installs Visual C++ 2015-2022 x64 redistributable silently if missing
   (one scoped UAC prompt). Skipped if already installed.
5. Creates Start Menu shortcut. Optional desktop shortcut via checkbox.

## Launcher behaviour at first run

1. Opens `%APPDATA%\AutoEditLite\logs\launcher.log` and writes OS build,
   CPU + AVX2 flag, install dir, full PATH. Always written **first** so
   crash diagnostics survive any later failure.
2. Probes for AVX2 (`IsProcessorFeaturePresent`). Warns up-front rather
   than letting `ctranslate2` crash inside Python.
3. Runs a Python import self-check for `faster_whisper`, `ctranslate2`,
   `anthropic`, `ffmpeg`, `dotenv`, `opentimelineio`. On failure, parses
   the `ImportError` and surfaces "missing module X — re-run installer
   to repair" instead of a Python stack trace.
4. If `.env` is missing or empty, opens the API-key dialog (windowed
   variant) or reads from stdin (CLI variant).
5. If the Whisper model dir is absent from `%APPDATA%\AutoEditLite\models`,
   shows a "First-run setup: downloading Whisper model (~1.5 GB)" modal
   with a marquee progress bar and runs `WhisperModel(size)` to pull the
   model before handing off to `app\main.py`.
6. Spawns `py\python.exe app\main.py <forwarded args>`. The windowed
   variant captures stdout/stderr to `logs\runtime.log`; the CLI variant
   inherits the parent terminal.

## CPU floor

The bundled `ctranslate2` wheel requires AVX2. Pre-Haswell Intel CPUs
(2013 and older) and pre-Zen AMD CPUs will trip the launcher's AVX2
warning. The build records the resolved ctranslate2 version into
`build\ctranslate2-resolved.txt` for forensic purposes.

If you need to support pre-AVX2 CPUs, drop an alternate wheel into
`installer\fallback-wheels\` and extend `Launcher.Run()` in `Program.cs`
to swap it in before the import self-check.

## Signing

Unsigned installers hit SmartScreen ("Windows protected your PC").
End-users see *More info → Run anyway*. To remove the prompt:

```powershell
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
    /a /n "Your Publisher Name" dist\AutoEditLite-Setup.exe
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
    /a /n "Your Publisher Name" dist\AutoEditLite-Portable-*.zip
```

Use Azure Trusted Signing or a DigiCert EV code-signing certificate.
The CI workflow at `.github\workflows\release-installer.yml` shells out
to a `Sign-Binary` step that is a no-op when the secrets are absent —
local builds just skip signing.
