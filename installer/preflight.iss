// ============================================================================
//  preflight.iss — Pascal [Code] helpers for AutoEditLite.iss
//
//  Provides:
//    - VCRedistNeeded()        Check for VC++ 2015-2022 x64 runtime
//    - IsPremiereInstalled()   Triple-check Premiere detection
//    - PreflightChecks()       Disk + Windows version gate
//    - API key wizard page     Collects ANTHROPIC_API_KEY, writes .env
//    - CurUninstallStepChanged Offers full wipe of %APPDATA%\AutoEditLite
// ============================================================================

const
  VCRedistKey = 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';

var
  ApiKeyPage: TInputQueryWizardPage;
  PremiereDetectedVersion: String;

// ---------------------------------------------------------------------------
//  VC++ runtime detection — used as a Check function on the [Run] entry and
//  the [Files] entry for the bundled VC_redist installer.
// ---------------------------------------------------------------------------
function VCRedistNeeded(): Boolean;
var
  Installed: Cardinal;
begin
  if RegQueryDWordValue(HKEY_LOCAL_MACHINE, VCRedistKey, 'Installed', Installed) then
    Result := Installed <> 1
  else
    Result := True;
end;

// ---------------------------------------------------------------------------
//  Premiere detection — three independent signals.
//  Sets PremiereDetectedVersion as a side effect so we can surface the
//  detected version in the finished page.
// ---------------------------------------------------------------------------
function FindPremiereExecutable(): String;
var
  ProgFiles: String;
  FindRec: TFindRec;
  CandidatePath: String;
begin
  Result := '';
  ProgFiles := ExpandConstant('{commonpf}');
  if FindFirst(ProgFiles + '\Adobe\Adobe Premiere Pro *', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          CandidatePath := ProgFiles + '\Adobe\' + FindRec.Name + '\Adobe Premiere Pro.exe';
          if FileExists(CandidatePath) then
          begin
            Result := FindRec.Name;
            Exit;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function IsPremiereInstalled(): Boolean;
var
  CepExtDir: String;
  Subkeys: TArrayOfString;
begin
  // (1) Registry under HKLM\SOFTWARE\Adobe\Premiere Pro
  if RegGetSubkeyNames(HKEY_LOCAL_MACHINE, 'SOFTWARE\Adobe\Premiere Pro', Subkeys) then
  begin
    if GetArrayLength(Subkeys) > 0 then
    begin
      PremiereDetectedVersion := 'Premiere Pro ' + Subkeys[GetArrayLength(Subkeys) - 1];
      Result := True;
      Exit;
    end;
  end;

  // (2) Adobe Premiere Pro.exe under %ProgramFiles%\Adobe\Adobe Premiere Pro *
  PremiereDetectedVersion := FindPremiereExecutable();
  if PremiereDetectedVersion <> '' then
  begin
    Result := True;
    Exit;
  end;

  // (3) %APPDATA%\Adobe\CEP\extensions — only meaningful if Premiere has
  //     ever launched on this user account
  CepExtDir := ExpandConstant('{userappdata}\Adobe\CEP\extensions');
  if DirExists(CepExtDir) then
  begin
    PremiereDetectedVersion := '(detected via CEP folder)';
    Result := True;
    Exit;
  end;

  PremiereDetectedVersion := '';
  Result := False;
end;

// ---------------------------------------------------------------------------
//  Disk + Windows version preflight. Runs from InitializeSetup.
// ---------------------------------------------------------------------------
function PreflightChecks(): Boolean;
var
  FreeMB: Cardinal;
  TotalMB: Cardinal;
  TargetDrive: String;
begin
  Result := True;

  // Need ~600 MB for the bundled install + headroom for the 1.5 GB model
  // cache the user will download on first run. 4 GB total is comfortable.
  // GetSpaceOnDisk signature: (DriveRoot, InMegabytes, var Free, var Total: Cardinal).
  TargetDrive := ExtractFileDrive(ExpandConstant('{localappdata}'));
  if GetSpaceOnDisk(TargetDrive, True, FreeMB, TotalMB) then
  begin
    if FreeMB < 4096 then
    begin
      MsgBox('AutoEdit-Lite needs at least 4 GB free on ' + TargetDrive + #13#10 +
             'Currently free: ' + IntToStr(FreeMB) + ' MB.' + #13#10 + #13#10 +
             'Free up space and run setup again.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;

  // x64 enforcement is handled by ArchitecturesAllowed=x64 in [Setup];
  // the installer EXE itself won't run on 32-bit Windows.
end;

function InitializeSetup(): Boolean;
begin
  Result := PreflightChecks();
end;

// ---------------------------------------------------------------------------
//  Custom wizard page: ANTHROPIC_API_KEY entry.
//  Written to %APPDATA%\AutoEditLite\.env after install.
// ---------------------------------------------------------------------------
procedure InitializeWizard();
begin
  ApiKeyPage := CreateInputQueryPage(wpSelectTasks,
    'Anthropic API Key',
    'Enter your Anthropic API key so AutoEdit-Lite can call Claude.',
    'You can paste it now or skip and add it later by editing' + #13#10 +
    '%APPDATA%\AutoEditLite\.env' + #13#10 + #13#10 +
    'Get a free key at: https://console.anthropic.com/');
  ApiKeyPage.Add('API key (starts with sk-ant-):', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Key: String;
begin
  Result := True;
  if CurPageID = ApiKeyPage.ID then
  begin
    Key := Trim(ApiKeyPage.Values[0]);
    if (Key <> '') and (Pos('sk-ant', Key) <> 1) then
    begin
      if MsgBox('That key does not start with "sk-ant-".' + #13#10 +
                'Save it anyway?', mbConfirmation, MB_YESNO) <> IDYES then
        Result := False;
    end;
  end;
end;

procedure WriteEnvFile();
var
  EnvDir, EnvPath, AppEnvPath: String;
  Key: String;
  Lines: TArrayOfString;
begin
  Key := Trim(ApiKeyPage.Values[0]);
  if Key = '' then Exit;

  // Survives uninstall (with default keep-data choice) — primary source.
  EnvDir := ExpandConstant('{userappdata}\AutoEditLite');
  ForceDirectories(EnvDir);
  EnvPath := EnvDir + '\.env';

  // Co-located with main.py so the Premiere CEP panel's spawned Python
  // finds the key via load_dotenv() — its child_process.spawn uses
  // backendPath as cwd, and load_dotenv searches the cwd.
  AppEnvPath := ExpandConstant('{app}\app\.env');

  SetArrayLength(Lines, 1);
  Lines[0] := 'ANTHROPIC_API_KEY=' + Key;
  SaveStringsToFile(EnvPath, Lines, False);
  SaveStringsToFile(AppEnvPath, Lines, False);
end;

// ---------------------------------------------------------------------------
//  Write %APPDATA%\AutoEdit\settings.json — the bridge the Premiere CEP
//  panel reads on first launch to discover where the Python backend lives.
//  See installerSettingsPath() and the loadSettings() fallback in
//  premiere-plugin\com.autoedit.premiere\client\main.js.
// ---------------------------------------------------------------------------
procedure WriteSettingsJson();
var
  SettingsDir, SettingsPath: String;
  BackendPath, PythonPath: String;
  Lines: TArrayOfString;
begin
  SettingsDir := ExpandConstant('{userappdata}\AutoEdit');
  ForceDirectories(SettingsDir);
  SettingsPath := SettingsDir + '\settings.json';

  BackendPath := ExpandConstant('{app}\app');
  PythonPath  := ExpandConstant('{app}\py\python.exe');

  // JSON requires escaped backslashes in strings.
  StringChangeEx(BackendPath, '\', '\\', True);
  StringChangeEx(PythonPath,  '\', '\\', True);

  SetArrayLength(Lines, 4);
  Lines[0] := '{';
  Lines[1] := '  "backendPath": "' + BackendPath + '",';
  Lines[2] := '  "pythonPath":  "' + PythonPath  + '"';
  Lines[3] := '}';
  SaveStringsToFile(SettingsPath, Lines, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteEnvFile();
    WriteSettingsJson();
  end;
end;

// ---------------------------------------------------------------------------
//  Uninstall: optional full-wipe checkbox for %APPDATA%\AutoEditLite.
//  By default we keep .env and the 1.5 GB Whisper model cache — reinstalls
//  should not redownload.
// ---------------------------------------------------------------------------
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\AutoEditLite');
    if DirExists(AppDataDir) then
    begin
      if MsgBox('Also delete your API key and the downloaded Whisper model cache?' + #13#10 +
               '(' + AppDataDir + ')' + #13#10 + #13#10 +
               'Click No to keep them for a future reinstall.',
               mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(AppDataDir, True, True, True);
      end;
    end;
  end;
end;
