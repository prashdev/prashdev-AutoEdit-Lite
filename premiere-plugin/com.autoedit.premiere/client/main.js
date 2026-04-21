/**
 * main.js — AutoEdit CEP panel logic v2.1
 *
 * Fix 1: On startup, read installer-written settings.json from
 *         %APPDATA%\AutoEdit\settings.json (Windows) or
 *         ~/Library/Application Support/AutoEdit/settings.json (Mac)
 *         and merge into localStorage so the panel auto-configures
 *         after a clean install without requiring the folder dialog.
 *
 * Fix 2: When the ExtendScript folder dialog fails (common on Windows
 *         with unsigned/debug extensions), reveal a plain text-input
 *         so the user can type the path manually instead of seeing a
 *         button that silently does nothing.
 */

(function () {
  "use strict";

  var csInterface    = new CSInterface();
  var path           = require("path");
  var os             = require("os");
  var fs             = require("fs");
  var child_process  = require("child_process");

  // ── State ──────────────────────────────────────────────────────────────
  var settings    = { backendPath: "", pythonPath: "" };
  var lastXmlPath = "";
  var currentStep = 0;
  var logVisible  = false;

  // ── DOM ────────────────────────────────────────────────────────────────
  var screenSetup     = document.getElementById("screen-setup");
  var screenMain      = document.getElementById("screen-main");
  var btnChoose       = document.getElementById("btn-choose-backend");
  var setupManual     = document.getElementById("setup-manual");
  var setupError      = document.getElementById("setup-error");
  var inputManualPath = document.getElementById("input-manual-path");
  var btnSetPath      = document.getElementById("btn-set-path");
  var pathError       = document.getElementById("path-error");
  var btnSettings     = document.getElementById("btn-settings");
  var btnBrowse       = document.getElementById("btn-browse");
  var fileDisplay     = document.getElementById("file-display");
  var selectModel     = document.getElementById("select-model");
  var selectQuality   = document.getElementById("select-quality");
  var btnGenerate     = document.getElementById("btn-generate");
  var sectionProgress = document.getElementById("section-progress");
  var sectionResult   = document.getElementById("section-result");
  var btnLogToggle    = document.getElementById("btn-log-toggle");
  var logBox          = document.getElementById("log-box");
  var logText         = document.getElementById("log-text");
  var resultBanner    = document.getElementById("result-banner");
  var resultIcon      = document.getElementById("result-icon");
  var resultTitle     = document.getElementById("result-title");
  var resultStats     = document.getElementById("result-stats");
  var statOriginal    = document.getElementById("stat-original");
  var statEdited      = document.getElementById("stat-edited");
  var statBadge       = document.getElementById("stat-badge");
  var btnImport       = document.getElementById("btn-import");
  var importHint      = document.getElementById("import-hint");
  var btnReset        = document.getElementById("btn-reset");

  var videoPath = "";

  // ── Settings ───────────────────────────────────────────────────────────
  function installerSettingsPath() {
    if (os.platform() === "win32") {
      var appData = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
      return path.join(appData, "AutoEdit", "settings.json");
    }
    return path.join(os.homedir(), "Library", "Application Support", "AutoEdit", "settings.json");
  }

  function loadSettings() {
    // 1. Try localStorage (fastest — already synced from a previous session)
    try {
      var raw = localStorage.getItem("autoedit_settings_v2");
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed.backendPath) {
          settings = parsed;
          return;
        }
      }
    } catch (e) {}

    // 2. Try installer-written JSON (present after a clean install on Windows/Mac)
    try {
      var installerFile = installerSettingsPath();
      if (fs.existsSync(installerFile)) {
        var installerRaw = fs.readFileSync(installerFile, "utf8");
        var installerParsed = JSON.parse(installerRaw);
        if (installerParsed.backendPath) {
          settings = installerParsed;
          saveSettings();  // mirror into localStorage for next time
        }
      }
    } catch (e) {}
  }

  function saveSettings() {
    localStorage.setItem("autoedit_settings_v2", JSON.stringify(settings));
  }

  function detectPython() {
    var candidates = os.platform() === "win32"
      ? [
          "C:\\Program Files\\Python312\\python.exe",
          "C:\\Program Files\\Python311\\python.exe",
          "C:\\Program Files\\Python310\\python.exe",
          "python",
        ]
      : [
          "/opt/homebrew/bin/python3",
          "/usr/local/bin/python3",
          "/usr/bin/python3",
          "python3",
        ];

    for (var i = 0; i < candidates.length; i++) {
      try {
        var r = child_process.spawnSync(candidates[i], ["--version"]);
        if (r.status === 0) return candidates[i];
      } catch (e) {}
    }
    return os.platform() === "win32" ? "python" : "python3";
  }

  function isConfigured() {
    return !!(settings.backendPath &&
              fs.existsSync(path.join(settings.backendPath, "main.py")));
  }

  // ── Init ───────────────────────────────────────────────────────────────
  loadSettings();
  isConfigured() ? showMain() : showSetup();

  // ── Setup — folder dialog (with graceful fallback) ─────────────────────
  btnChoose.addEventListener("click", function () {
    csInterface.evalScript(
      'var f = Folder.selectDialog("Select your autoedit-lite folder"); f ? f.fsName : ""',
      function (sel) {
        // evalScript failed — ExtendScript bridge not available (common on Windows
        // with debug/unsigned extensions). Show the manual text input instead.
        if (!sel || sel === "EvalScript error." || sel.indexOf("EvalScript error") !== -1) {
          setupError.textContent =
            "Folder dialog is unavailable on this machine. " +
            "Please type the path to your autoedit-lite folder below.";
          setupManual.classList.remove("hidden");
          inputManualPath.focus();
          return;
        }

        sel = sel.trim();
        if (!validateAndApplyPath(sel)) {
          // Validation failed — show manual fallback so user can correct it
          setupError.textContent = "That folder does not contain main.py. Please check and try again.";
          setupManual.classList.remove("hidden");
          inputManualPath.value = sel;
          inputManualPath.focus();
        }
      }
    );
  });

  // ── Setup — manual path input ──────────────────────────────────────────
  btnSetPath.addEventListener("click", applyManualPath);

  inputManualPath.addEventListener("keydown", function (e) {
    if (e.key === "Enter") applyManualPath();
  });

  function applyManualPath() {
    var typed = (inputManualPath.value || "").trim();
    if (!typed) return;
    pathError.classList.add("hidden");
    if (!validateAndApplyPath(typed)) {
      pathError.classList.remove("hidden");
    }
  }

  function validateAndApplyPath(folderPath) {
    if (!fs.existsSync(path.join(folderPath, "main.py"))) return false;
    settings.backendPath = folderPath;
    settings.pythonPath  = settings.pythonPath || detectPython();
    saveSettings();
    showMain();
    return true;
  }

  // ── Settings gear icon ─────────────────────────────────────────────────
  btnSettings.addEventListener("click", showSetup);

  // ── Browse video ───────────────────────────────────────────────────────
  btnBrowse.addEventListener("click", function () {
    csInterface.evalScript(
      'var f = File.openDialog("Select a video file", "*.mp4;*.mov;*.mkv;*.webm", false); f ? f.fsName : ""',
      function (fp) {
        if (!fp || fp === "EvalScript error." || fp.indexOf("EvalScript error") !== -1) {
          // Browse dialog failed — ask user to type path manually via a simple prompt
          var typed = window.prompt("Folder dialog unavailable.\nPaste the full path to your video file:");
          if (typed && typed.trim()) {
            applyVideoPath(typed.trim());
          }
          return;
        }
        applyVideoPath(fp.trim());
      }
    );
  });

  function applyVideoPath(fp) {
    if (!fp || !fs.existsSync(fp)) return;
    videoPath = fp;
    fileDisplay.textContent = path.basename(videoPath);
    fileDisplay.classList.add("has-file");
    fileDisplay.title = videoPath;
    btnGenerate.disabled = false;
  }

  // ── Generate ───────────────────────────────────────────────────────────
  btnGenerate.addEventListener("click", function () {
    if (!videoPath) return;

    var videoDir  = path.dirname(videoPath);
    var videoBase = path.basename(videoPath, path.extname(videoPath));
    lastXmlPath   = path.join(videoDir, videoBase + "_autoedit.xml");

    var python = settings.pythonPath || detectPython();
    var args   = [
      path.join(settings.backendPath, "main.py"),
      "--input",   videoPath,
      "--mode",    "premiere",
      "--model",   selectModel.value,
      "--quality", selectQuality.value,
      "--output",  path.join(videoDir, videoBase + "_autoedit.mp4"),
    ];

    startRun();

    var proc = child_process.spawn(python, args, { cwd: settings.backendPath });

    proc.stdout.on("data", function (data) {
      var text = data.toString();
      appendLog(text);
      updateSteps(text);
    });

    proc.stderr.on("data", function (data) {
      appendLog(data.toString());
    });

    proc.on("close", function (code) {
      if (code === 0 && fs.existsSync(lastXmlPath)) {
        setStepDone(4);
        showSuccess();
      } else {
        showError("Something went wrong. Toggle the log above to see what happened.");
      }
      btnGenerate.disabled = false;
      btnBrowse.disabled   = false;
    });

    proc.on("error", function (err) {
      showError("Could not start Python.\n" + err.message);
      btnGenerate.disabled = false;
      btnBrowse.disabled   = false;
    });
  });

  // ── Log toggle ─────────────────────────────────────────────────────────
  btnLogToggle.addEventListener("click", function () {
    logVisible = !logVisible;
    logBox.classList.toggle("hidden", !logVisible);
    btnLogToggle.textContent = logVisible ? "Hide log ▴" : "Show log ▾";
  });

  // ── Import ─────────────────────────────────────────────────────────────
  btnImport.addEventListener("click", function () {
    var script = 'importXmlSequence("' + lastXmlPath.replace(/\\/g, "\\\\") + '")';
    csInterface.evalScript(script, function (result) {
      if (result === "SUCCESS") {
        resultTitle.textContent = "Sequence imported into your project!";
        btnImport.disabled = true;
        importHint.classList.add("hidden");
      } else {
        importHint.textContent = "Auto-import failed — go to File → Import and pick: " + lastXmlPath;
        importHint.classList.remove("hidden");
      }
    });
  });

  btnReset.addEventListener("click", resetUI);

  // ── Step logic ─────────────────────────────────────────────────────────
  var stepKeywords = [
    { key: "[1/4]", step: 1 },
    { key: "[2/4]", step: 2 },
    { key: "[3/4]", step: 3 },
    { key: "[4/4]", step: 4 },
  ];

  function updateSteps(text) {
    stepKeywords.forEach(function (s) {
      if (text.indexOf(s.key) !== -1) {
        if (currentStep > 0) setStepDone(currentStep);
        setStepActive(s.step);
        currentStep = s.step;
      }
    });
  }

  function setStepActive(n) {
    var el = document.getElementById("step-" + n);
    if (el) { el.classList.remove("done"); el.classList.add("active"); }
  }

  function setStepDone(n) {
    var el = document.getElementById("step-" + n);
    if (el) { el.classList.remove("active"); el.classList.add("done"); }
  }

  function resetSteps() {
    for (var i = 1; i <= 4; i++) {
      var el = document.getElementById("step-" + i);
      if (el) { el.classList.remove("active", "done"); }
    }
    currentStep = 0;
  }

  // ── Parse result stats from log ────────────────────────────────────────
  function parseStats(log) {
    var orig, edited, pct;
    var mOrig    = log.match(/Original duration\s*:\s*([0-9:]+)/);
    var mEdited  = log.match(/Edited duration\s*:\s*([0-9:]+)/);
    var mReduct  = log.match(/Reduction\s*:\s*(\d+)%/);
    if (mOrig)   orig   = mOrig[1];
    if (mEdited) edited = mEdited[1];
    if (mReduct) pct    = mReduct[1];
    return { orig: orig, edited: edited, pct: pct };
  }

  // ── UI transitions ─────────────────────────────────────────────────────
  function showSetup() {
    // Reset manual fallback state when returning to setup
    setupManual.classList.add("hidden");
    setupError.textContent = "";
    pathError.classList.add("hidden");
    inputManualPath.value = "";
    screenSetup.classList.remove("hidden");
    screenMain.classList.add("hidden");
  }

  function showMain() {
    screenSetup.classList.add("hidden");
    screenMain.classList.remove("hidden");
    sectionProgress.classList.add("hidden");
    sectionResult.classList.add("hidden");
  }

  function startRun() {
    btnGenerate.disabled = true;
    btnBrowse.disabled   = true;
    sectionResult.classList.add("hidden");
    sectionProgress.classList.remove("hidden");
    logText.textContent = "";
    if (!logVisible) { logBox.classList.add("hidden"); }
    resetSteps();
    setStepActive(1);
    currentStep = 1;
  }

  function showSuccess() {
    var stats = parseStats(logText.textContent);

    resultBanner.className    = "result-banner success";
    resultIcon.textContent    = "✓";
    resultTitle.textContent   = "Rough cut ready!";

    if (stats.orig && stats.edited && stats.pct) {
      statOriginal.textContent = stats.orig;
      statEdited.textContent   = stats.edited;
      statBadge.textContent    = stats.pct + "% shorter";
      resultStats.classList.remove("hidden");
    }

    btnImport.classList.remove("hidden");
    btnImport.disabled = false;
    importHint.classList.add("hidden");
    sectionResult.classList.remove("hidden");
  }

  function showError(msg) {
    resultBanner.className  = "result-banner error";
    resultIcon.textContent  = "✕";
    resultTitle.textContent = msg;
    resultStats.classList.add("hidden");
    btnImport.classList.add("hidden");
    importHint.classList.add("hidden");
    sectionResult.classList.remove("hidden");

    // Auto-show log on error
    if (!logVisible) {
      logVisible = true;
      logBox.classList.remove("hidden");
      btnLogToggle.textContent = "Hide log ▴";
    }
  }

  function appendLog(text) {
    logText.textContent += text;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function resetUI() {
    videoPath   = "";
    lastXmlPath = "";
    fileDisplay.textContent = "No file selected";
    fileDisplay.classList.remove("has-file");
    fileDisplay.title = "";
    btnGenerate.disabled = true;
    logText.textContent  = "";
    logVisible = false;
    logBox.classList.add("hidden");
    btnLogToggle.textContent = "Show log ▾";
    sectionProgress.classList.add("hidden");
    sectionResult.classList.add("hidden");
    resetSteps();
  }

})();
