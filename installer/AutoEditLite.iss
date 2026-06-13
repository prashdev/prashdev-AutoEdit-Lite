; ============================================================================
;  AutoEdit-Lite — Inno Setup script
;  Produces: dist\AutoEditLite-Setup.exe
;
;  Build pipeline (installer\build.ps1) stages dependencies under .\build\
;  before running iscc.exe on this file:
;
;    build\py\       embedded Python 3.11 + Lib\site-packages
;    build\ff\bin\   ffmpeg.exe, ffprobe.exe
;    build\app\      repo source (main.py, transcribe.py, ...)
;    build\bin\      AutoEditLite.exe + AutoEditLite-CLI.exe (launcher)
;    build\redist\   VC_redist.x64.exe
; ============================================================================

#define AppName       "AutoEdit-Lite"
#define AppPublisher  "prashdev"
#define AppVersion    GetEnv("AUTOEDIT_VERSION")
#if AppVersion == ""
  #define AppVersion  "0.1.0.0"
#endif
#define AppExe        "AutoEditLite.exe"
#define AppCliExe     "AutoEditLite-CLI.exe"
#define AppURL        "https://github.com/prashdev/prashdev-AutoEdit-Lite"

[Setup]
AppId={{6F2A3B4C-9D1E-4F0A-8B7C-AE12C4D5E6F7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
VersionInfoVersion={#AppVersion}

; --- Per-user install. No UAC for the installer itself. ---------------------
; The two operations that may need elevation (VC++ redist install,
; HKLM probe) are handled in [Code] with scoped runas / read-only access.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline

DefaultDirName={localappdata}\Programs\AutoEditLite
DefaultGroupName=AutoEdit-Lite
DisableProgramGroupPage=yes
DisableDirPage=no

; --- Platform floor ---------------------------------------------------------
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

OutputDir=dist
OutputBaseFilename=AutoEditLite-Setup
#if FileExists(AddBackslash(SourcePath) + "icon.ico")
SetupIconFile=icon.ico
#endif
WizardStyle=modern
Compression=lzma2/ultra
SolidCompression=yes
LZMAUseSeparateProcess=yes

UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}

; --- License / Readme (optional, both gracefully skipped if missing) --------
; LicenseFile=..\LICENSE
; InfoBeforeFile=README-before.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
    GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; All paths are relative to this .iss file. build.ps1 stages everything
; under installer\build\ before invoking ISCC.

; Embedded Python 3.11 (short folder name keeps deep paths under MAX_PATH)
Source: "build\py\*"; DestDir: "{app}\py"; Flags: ignoreversion recursesubdirs createallsubdirs

; FFmpeg (essentials build)
Source: "build\ff\*"; DestDir: "{app}\ff"; Flags: ignoreversion recursesubdirs createallsubdirs

; Application source
Source: "build\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

; Premiere CEP extension — the panel that shows up in
; Premiere Pro under Window > Extensions > AutoEdit.
; Uses the SIGNED build (see build.ps1 step 6c). Premiere Pro 2024+
; requires a valid signature; PlayerDebugMode lets it trust a self-signed
; cert but does not skip the signature check itself.
; Installed unconditionally so it's wired up even if the user installs
; Premiere AFTER AutoEdit-Lite.
Source: "build\cep-signed\com.autoedit.premiere\*"; \
    DestDir: "{userappdata}\Adobe\CEP\extensions\com.autoedit.premiere"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; Launcher binaries
Source: "build\bin\{#AppExe}";    DestDir: "{app}"; Flags: ignoreversion
Source: "build\bin\{#AppCliExe}"; DestDir: "{app}"; Flags: ignoreversion

; VC++ redist installer — kept in {tmp}, deleted after [Run]
Source: "build\redist\VC_redist.x64.exe"; DestDir: "{tmp}"; \
    Flags: deleteafterinstall; Check: VCRedistNeeded

[Run]
; Install VC++ redist silently. Will trigger UAC ONCE for this single step.
; If the user declines elevation, we surface a warning and continue —
; the launcher's startup self-check will catch the missing DLL and offer
; a "Repair" path with a useful message.
Filename: "{tmp}\VC_redist.x64.exe"; \
    Parameters: "/install /quiet /norestart"; \
    StatusMsg: "Installing Visual C++ runtime..."; \
    Flags: waituntilterminated shellexec runascurrentuser; \
    Check: VCRedistNeeded

[Icons]
Name: "{group}\AutoEdit-Lite";        Filename: "{app}\{#AppExe}"
Name: "{group}\AutoEdit-Lite (CLI)";  Filename: "{app}\{#AppCliExe}"
Name: "{group}\Uninstall AutoEdit-Lite"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AutoEdit-Lite";  Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Premiere CEP PlayerDebugMode — required so Premiere will trust our
; self-signed extension certificate. HKCU only, no admin needed.
; Written unconditionally so the panel works once Premiere is installed
; (now or later). Covers Premiere Pro 2018 (CSXS 9) through 2026+ (CSXS 14).
Root: HKCU; Subkey: "Software\Adobe\CSXS.9";  ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.10"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.11"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.12"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.13"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.14"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"
Root: HKCU; Subkey: "Software\Adobe\CSXS.15"; ValueType: string; ValueName: "PlayerDebugMode"; ValueData: "1"

[Dirs]
; Pre-create per-user state directories so the launcher never has to.
Name: "{userappdata}\AutoEditLite";        Permissions: users-modify
Name: "{userappdata}\AutoEditLite\logs";   Permissions: users-modify
Name: "{userappdata}\AutoEditLite\models"; Permissions: users-modify
; Panel reads its bridge config from here — see WriteSettingsJson in preflight.iss.
Name: "{userappdata}\AutoEdit";            Permissions: users-modify

[UninstallDelete]
; Wipe logs but keep .env and models by default — see CurUninstallStepChanged
; in preflight.iss for the optional full-wipe prompt.
Type: filesandordirs; Name: "{userappdata}\AutoEditLite\logs"
; Remove the panel and its installer-written settings; rebuild on reinstall.
Type: filesandordirs; Name: "{userappdata}\Adobe\CEP\extensions\com.autoedit.premiere"
Type: files;          Name: "{userappdata}\AutoEdit\settings.json"

[Code]
// Pascal helpers + custom wizard pages live in a separate file
#include "preflight.iss"
