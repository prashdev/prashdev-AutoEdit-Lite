/**
 * main.js — AutoEdit CEP panel logic v2.1
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
  var lastSrtPath = "";
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
  var selectDuration  = document.getElementById("select-duration");
  var selectAspect    = document.getElementById("select-aspect");
  var selectPlatform  = document.getElementById("select-platform");
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
  var outputFiles     = document.getElementById("output-files");
  var outputXmlPath   = document.getElementById("output-xml-path");
  var outputSrtPath   = document.getElementById("output-srt-path");
  var btnImport       = document.getElementById("btn-import");
  var importHint      = document.getElementById("import-hint");
  var btnImportSrt    = document.getElementById("btn-import-srt");
  var importSrtHint   = document.getElementById("import-srt-hint");
  var losslesscutHint = document.getElementById("losslesscut-hint");
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
    // 1. Try localStorage (fastest — already synced from a previous session).
    //    Only trust the cached path if main.py is still there. Without this
    //    a stale backendPath from a previous install would silently mask the
    //    settings.json a fresh installer just wrote.
    try {
      var raw = localStorage.getItem("autoedit_settings_v2");
      if (raw) {
        var parsed = JSON.parse(raw);
        if (parsed.backendPath &&
            fs.existsSync(path.join(parsed.backendPath, "main.py"))) {
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
        if (installerRaw.charCodeAt(0) === 0xFEFF) installerRaw = installerRaw.slice(1); // strip BOM if any
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

    var videoDir   = path.dirname(videoPath);
    var videoBase  = path.basename(videoPath, path.extname(videoPath));
    // All outputs go into a dedicated subfolder next to the source video:
    //   VideoName_autoedit/VideoName_autoedit.xml
    //   VideoName_autoedit/VideoName_autoedit.srt
    //   VideoName_autoedit/logs/transcript.json
    var outputDir  = path.join(videoDir, videoBase + "_autoedit");
    if (!fs.existsSync(outputDir)) { fs.mkdirSync(outputDir, { recursive: true }); }
    lastXmlPath    = path.join(outputDir, videoBase + "_autoedit.xml");
    lastSrtPath    = path.join(outputDir, videoBase + "_autoedit.srt");

    var python = settings.pythonPath || detectPython();
    var args   = [
      path.join(settings.backendPath, "main.py"),
      "--input",           videoPath,
      "--mode",            "premiere",
      "--model",           selectModel.value,
      "--quality",         selectQuality.value,
      "--target-duration", selectDuration.value,
      "--aspect-ratio",    selectAspect.value,
      "--platform",        selectPlatform.value,
      "--output",          path.join(outputDir, videoBase + "_autoedit.mp4"),
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
        showError("Something went wrong. Toggle the log above to see details.");
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

  // ── Import XML ─────────────────────────────────────────────────────────
  btnImport.addEventListener("click", function () {
    var escaped = lastXmlPath.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    csInterface.evalScript('importXmlSequence("' + escaped + '")', function (result) {
      if (result === "SUCCESS") {
        resultTitle.textContent = "Timeline imported!";
        btnImport.disabled = true;
        importHint.classList.add("hidden");
      } else {
        importHint.textContent = "Auto-import failed. Go to File → Import → pick: " + lastXmlPath;
        importHint.classList.remove("hidden");
      }
    });
  });

  // ── Import SRT ─────────────────────────────────────────────────────────
  btnImportSrt.addEventListener("click", function () {
    if (!lastSrtPath || !fs.existsSync(lastSrtPath)) {
      importSrtHint.textContent = "SRT file not found: " + lastSrtPath;
      importSrtHint.classList.remove("hidden");
      return;
    }
    var escaped = lastSrtPath.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    csInterface.evalScript('importSrtFile("' + escaped + '")', function (result) {
      if (result === "SUCCESS") {
        btnImportSrt.textContent = "✓ Subtitles imported";
        btnImportSrt.disabled = true;
        importSrtHint.classList.add("hidden");
      } else {
        importSrtHint.textContent = "Auto-import failed. Go to File → Import → pick: " + lastSrtPath;
        importSrtHint.classList.remove("hidden");
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
    var mOrig   = log.match(/Original duration\s*:\s*([0-9:]+)/);
    var mEdited = log.match(/Edited duration\s*:\s*([0-9:]+)/);
    var mReduct = log.match(/Reduction\s*:\s*(\d+)%/);
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

    resultBanner.className  = "result-banner success";
    resultIcon.textContent  = "✓";
    resultTitle.textContent = "Rough cut ready!";

    if (stats.orig && stats.edited && stats.pct) {
      statOriginal.textContent = stats.orig;
      statEdited.textContent   = stats.edited;
      statBadge.textContent    = stats.pct + "% shorter";
      resultStats.classList.remove("hidden");
    }

    // Show output file paths
    if (outputXmlPath) outputXmlPath.textContent = path.basename(lastXmlPath);
    if (outputSrtPath) outputSrtPath.textContent = path.basename(lastSrtPath);
    outputFiles.classList.remove("hidden");

    // XML import button
    btnImport.textContent = "↓  Import Timeline (.xml)";
    btnImport.classList.remove("hidden");
    btnImport.disabled = false;
    importHint.classList.add("hidden");

    // SRT import button — only show if SRT was actually created
    if (fs.existsSync(lastSrtPath)) {
      btnImportSrt.textContent = "↓  Import Subtitles (.srt)";
      btnImportSrt.classList.remove("hidden");
      btnImportSrt.disabled = false;
      importSrtHint.classList.add("hidden");
    }

    losslesscutHint.classList.remove("hidden");
    sectionResult.classList.remove("hidden");
  }

  function showError(msg) {
    resultBanner.className  = "result-banner error";
    resultIcon.textContent  = "✕";
    resultTitle.textContent = msg;
    resultStats.classList.add("hidden");
    outputFiles.classList.add("hidden");
    btnImport.classList.add("hidden");
    btnImportSrt.classList.add("hidden");
    importHint.classList.add("hidden");
    importSrtHint.classList.add("hidden");
    losslesscutHint.classList.add("hidden");
    sectionResult.classList.remove("hidden");

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
    lastSrtPath = "";
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
    outputFiles.classList.add("hidden");
    btnImportSrt.classList.add("hidden");
    importSrtHint.classList.add("hidden");
    losslesscutHint.classList.add("hidden");
    resetSteps();
  }

})();
