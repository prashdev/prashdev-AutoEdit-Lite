// AutoEdit-Lite launcher
//
// Replaces run_windows.bat. Resolves the embedded Python + ffmpeg, runs a
// dependency self-check, prompts for the Anthropic API key if missing,
// preloads the Whisper model on first run, and spawns app/main.py.
//
// Two binaries are produced from this single source via two csproj files:
//   AutoEditLite.exe      — WinExe (no console flash). Defines WINDOWED.
//   AutoEditLite-CLI.exe  — Exe (console attached). No WINDOWED constant.

using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            Logger.Init();
            return Launcher.Run(args);
        }
        catch (Exception ex)
        {
            Logger.Crash(ex);
            UI.Error($"AutoEdit-Lite failed to launch.\n\n{ex.Message}\n\nFull log: {Logger.LogPath}");
            return 1;
        }
    }
}

internal static class Paths
{
    public static string InstallDir =>
        AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
    public static string AppDataDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "AutoEditLite");
    public static string PythonExe  => Path.Combine(InstallDir, "py",  "python.exe");
    public static string FfmpegBin  => Path.Combine(InstallDir, "ff",  "bin");
    public static string AppDir     => Path.Combine(InstallDir, "app");
    public static string MainPy     => Path.Combine(AppDir, "main.py");
    public static string EnvFile    => Path.Combine(AppDataDir, ".env");
    public static string ModelsDir  => Path.Combine(AppDataDir, "models");
    public static string LogsDir    => Path.Combine(AppDataDir, "logs");
    public static string RuntimeLog => Path.Combine(LogsDir, "runtime.log");
}

internal static class Logger
{
    public static string LogPath { get; private set; } = "";
    private static StreamWriter? _writer;
    private static readonly object _lock = new();

    public static void Init()
    {
        Directory.CreateDirectory(Paths.LogsDir);
        LogPath = Path.Combine(Paths.LogsDir, "launcher.log");
        // UTF-8 so em-dashes etc. in messages survive the round trip.
        _writer = new StreamWriter(LogPath, append: true, System.Text.Encoding.UTF8) { AutoFlush = true };
        Write("");
        Write("=== launcher started ===");
        Write($"timestamp:   {DateTime.Now:O}");
        Write($"os:          {Environment.OSVersion}");
        Write($"clr:         {Environment.Version}");
        Write($"install dir: {Paths.InstallDir}");
        Write($"appdata:     {Paths.AppDataDir}");
        Write($"avx2:        {CpuInfo.HasAvx2()}");
        Write($"PATH:        {Environment.GetEnvironmentVariable("PATH")}");
    }

    public static void Write(string line)
    {
        lock (_lock) { _writer?.WriteLine(line); }
    }

    public static void Crash(Exception ex) => Write($"FATAL: {ex}");
}

internal static class CpuInfo
{
    [DllImport("kernel32.dll")]
    private static extern bool IsProcessorFeaturePresent(uint feature);

    private const uint PF_AVX2_INSTRUCTIONS_AVAILABLE = 40;

    public static bool HasAvx2()
    {
        try { return IsProcessorFeaturePresent(PF_AVX2_INSTRUCTIONS_AVAILABLE); }
        catch { return false; }
    }
}

internal static class UI
{
    public static void Info(string msg)
    {
#if WINDOWED
        MessageBox.Show(msg, "AutoEdit-Lite", MessageBoxButtons.OK, MessageBoxIcon.Information);
#else
        Console.WriteLine(msg);
#endif
    }

    public static void Error(string msg)
    {
#if WINDOWED
        MessageBox.Show(msg, "AutoEdit-Lite", MessageBoxButtons.OK, MessageBoxIcon.Error);
#else
        Console.Error.WriteLine(msg);
#endif
    }

    public static void Warn(string msg)
    {
#if WINDOWED
        MessageBox.Show(msg, "AutoEdit-Lite", MessageBoxButtons.OK, MessageBoxIcon.Warning);
#else
        Console.WriteLine("WARN: " + msg);
#endif
    }
}

internal static class Launcher
{
    public static int Run(string[] args)
    {
        if (!File.Exists(Paths.PythonExe))
        {
            UI.Error($"Embedded Python missing at {Paths.PythonExe}.\nReinstall AutoEdit-Lite.");
            return 2;
        }
        if (!File.Exists(Paths.MainPy))
        {
            UI.Error($"Application source missing at {Paths.MainPy}.\nReinstall AutoEdit-Lite.");
            return 2;
        }

        // Process-scoped PATH only — never touches system PATH.
        Environment.SetEnvironmentVariable(
            "PATH",
            Paths.FfmpegBin + Path.PathSeparator + Environment.GetEnvironmentVariable("PATH"));

        Environment.SetEnvironmentVariable("HF_HOME", Paths.ModelsDir);
        Environment.SetEnvironmentVariable("CUDA_VISIBLE_DEVICES", "-1");

        if (!CpuInfo.HasAvx2())
        {
            Logger.Write("WARN: CPU lacks AVX2");
            UI.Warn("Your CPU does not support AVX2.\n\n" +
                    "faster-whisper (used for transcription) may fail to load. " +
                    "Continuing — see launcher.log if you hit errors.");
        }

        if (!DepCheck.Run(out var failedModule))
        {
            UI.Error($"AutoEdit-Lite cannot start.\nMissing Python module: {failedModule}\n\n" +
                     "Re-run the installer to repair.\n\n" +
                     $"Full log: {Logger.LogPath}");
            return 3;
        }

        // --help / -h / --version are introspection-only; don't gate them
        // on an API key or trigger a 1.5 GB model download.
        bool informational = IsInformationalInvocation(args);
        Logger.Write($"informational: {informational}");

        if (!informational)
        {
            if (!ApiKey.EnsurePresent())
            {
                Logger.Write("API key not provided.");
                UI.Error("No Anthropic API key configured. Set ANTHROPIC_API_KEY in:\n" + Paths.EnvFile);
                return 4;
            }

            var model = ExtractModelArg(args);
            if (!ModelCache.Has(model))
            {
                Logger.Write($"Model '{model}' not cached -- preloading.");
                if (!ModelPreload.Run(model))
                {
                    UI.Error("Whisper model download failed. Check your internet connection.");
                    return 5;
                }
            }
        }

        return SpawnPython(args);
    }

    private static bool IsInformationalInvocation(string[] args)
    {
        foreach (var a in args)
        {
            if (string.Equals(a, "--help", StringComparison.Ordinal) ||
                string.Equals(a, "-h",     StringComparison.Ordinal) ||
                string.Equals(a, "--version", StringComparison.Ordinal))
                return true;
        }
        return false;
    }

    private static string ExtractModelArg(string[] args)
    {
        for (int i = 0; i < args.Length - 1; i++)
            if (string.Equals(args[i], "--model", StringComparison.Ordinal))
                return args[i + 1];
        return "medium";
    }

    private static int SpawnPython(string[] args)
    {
        var psi = new ProcessStartInfo
        {
            FileName = Paths.PythonExe,
            WorkingDirectory = Paths.AppDir,
            UseShellExecute = false,
        };
        psi.ArgumentList.Add(Paths.MainPy);
        foreach (var a in args) psi.ArgumentList.Add(a);

        // Forward the API key as an env var so analyze.py's
        // `os.getenv("ANTHROPIC_API_KEY")` resolves without depending on
        // python-dotenv's CWD-relative .env search. The key lives in
        // %APPDATA%\AutoEditLite\.env, which the launcher already knows
        // how to read.
        var key = ApiKey.Read();
        if (!string.IsNullOrWhiteSpace(key))
        {
            psi.Environment["ANTHROPIC_API_KEY"] = key;
        }

#if WINDOWED
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError  = true;
        psi.CreateNoWindow = true;
#endif

        Logger.Write($"spawn: {Paths.PythonExe} {string.Join(" ", psi.ArgumentList)}");
        using var p = Process.Start(psi)!;

#if WINDOWED
        Directory.CreateDirectory(Paths.LogsDir);
        var rt = new StreamWriter(Paths.RuntimeLog, append: true) { AutoFlush = true };
        p.OutputDataReceived += (_, e) => { if (e.Data != null) rt.WriteLine(e.Data); };
        p.ErrorDataReceived  += (_, e) => { if (e.Data != null) rt.WriteLine("ERR " + e.Data); };
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
#endif
        p.WaitForExit();
        Logger.Write($"child exit: {p.ExitCode}");
        return p.ExitCode;
    }
}

internal static class DepCheck
{
    private const string Script =
        "import faster_whisper, ctranslate2, anthropic, ffmpeg, dotenv, opentimelineio; print('OK')";

    public static bool Run(out string failedModule)
    {
        failedModule = "";
        var psi = new ProcessStartInfo(Paths.PythonExe)
        {
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        psi.ArgumentList.Add("-c");
        psi.ArgumentList.Add(Script);

        using var p = Process.Start(psi)!;
        string outp = p.StandardOutput.ReadToEnd();
        string err  = p.StandardError.ReadToEnd();
        p.WaitForExit();
        Logger.Write($"depcheck stdout: {outp.Trim()}");
        if (err.Length > 0) Logger.Write($"depcheck stderr: {err.Trim()}");
        if (p.ExitCode == 0 && outp.Contains("OK")) return true;

        var m = Regex.Match(err, @"No module named '([^']+)'");
        failedModule = m.Success ? m.Groups[1].Value : "(unknown — see launcher.log)";
        return false;
    }
}

internal static class ModelCache
{
    public static bool Has(string size)
    {
        var dir = Path.Combine(Paths.ModelsDir, $"models--Systran--faster-whisper-{size}");
        return Directory.Exists(dir);
    }
}

internal static class ModelPreload
{
    public static bool Run(string size)
    {
        // Materialize the model into HF_HOME by instantiating WhisperModel.
        // faster-whisper writes progress to stderr; we tee it into launcher.log.
        var script =
            $"from faster_whisper import WhisperModel; " +
            $"WhisperModel('{size}', device='cpu', compute_type='int8'); " +
            $"print('PRELOAD_OK')";

        var psi = new ProcessStartInfo(Paths.PythonExe)
        {
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        psi.ArgumentList.Add("-c");
        psi.ArgumentList.Add(script);

#if WINDOWED
        return RunWithDialog(psi, size);
#else
        Console.WriteLine($"First-run setup: downloading Whisper '{size}' model (one-time, ~5-15 min)...");
        using var p = Process.Start(psi)!;
        p.OutputDataReceived += (_, e) => { if (e.Data != null) Console.WriteLine(e.Data); };
        p.ErrorDataReceived  += (_, e) => { if (e.Data != null) Console.Error.WriteLine(e.Data); };
        p.BeginOutputReadLine();
        p.BeginErrorReadLine();
        p.WaitForExit();
        return p.ExitCode == 0;
#endif
    }

#if WINDOWED
    private static bool RunWithDialog(ProcessStartInfo psi, string size)
    {
        bool ok = false;
        Exception? caught = null;

        var form = new Form
        {
            Text = "AutoEdit-Lite",
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterScreen,
            Width = 500, Height = 180,
            MaximizeBox = false, MinimizeBox = false, ControlBox = false,
        };
        form.Controls.Add(new Label
        {
            Text = $"First-run setup: downloading Whisper '{size}' model.\n" +
                   "This is a one-time download (~1.5 GB for 'medium'). " +
                   "5–15 minutes on a typical connection.\n\n" +
                   "Please don't close this window.",
            Top = 16, Left = 20, Width = 460, Height = 80,
        });
        form.Controls.Add(new ProgressBar
        {
            Style = ProgressBarStyle.Marquee,
            Top = 110, Left = 20, Width = 460, Height = 22,
            MarqueeAnimationSpeed = 30,
        });

        var worker = new Thread(() =>
        {
            try
            {
                using var p = Process.Start(psi)!;
                p.OutputDataReceived += (_, e) => { if (e.Data != null) Logger.Write("MODEL " + e.Data); };
                p.ErrorDataReceived  += (_, e) => { if (e.Data != null) Logger.Write("MODEL " + e.Data); };
                p.BeginOutputReadLine();
                p.BeginErrorReadLine();
                p.WaitForExit();
                ok = p.ExitCode == 0;
            }
            catch (Exception ex) { caught = ex; }
            try { form.BeginInvoke(new Action(() => form.Close())); } catch { }
        }) { IsBackground = true };

        form.Shown += (_, _) => worker.Start();
        form.ShowDialog();

        if (caught != null) Logger.Crash(caught);
        return ok;
    }
#endif
}

internal static class ApiKey
{
    private const string Prefix = "ANTHROPIC_API_KEY=";

    public static bool EnsurePresent()
    {
        Directory.CreateDirectory(Paths.AppDataDir);
        if (!string.IsNullOrWhiteSpace(Read())) return true;

        string? key;
#if WINDOWED
        key = Prompt();
#else
        Console.Write("Anthropic API key (sk-ant-...): ");
        key = Console.ReadLine()?.Trim();
#endif
        if (string.IsNullOrWhiteSpace(key)) return false;
        File.WriteAllText(Paths.EnvFile, Prefix + key + "\n");
        return true;
    }

    internal static string? Read()
    {
        if (!File.Exists(Paths.EnvFile)) return null;
        foreach (var raw in File.ReadAllLines(Paths.EnvFile))
        {
            var line = raw.Trim();
            if (line.StartsWith(Prefix, StringComparison.Ordinal))
                return line.Substring(Prefix.Length).Trim();
        }
        return null;
    }

#if WINDOWED
    private static string? Prompt()
    {
        var form = new Form
        {
            Text = "AutoEdit-Lite — Anthropic API key",
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterScreen,
            Width = 540, Height = 220,
            MaximizeBox = false, MinimizeBox = false,
        };
        form.Controls.Add(new Label
        {
            Text = "Paste your Anthropic API key (starts with sk-ant-).\n" +
                   "Get one at https://console.anthropic.com/",
            Top = 16, Left = 20, Width = 490, Height = 48,
        });
        var box = new TextBox { Top = 78, Left = 20, Width = 490 };
        var ok = new Button { Text = "Save", Top = 130, Left = 340, Width = 80, DialogResult = DialogResult.OK };
        var cancel = new Button { Text = "Cancel", Top = 130, Left = 430, Width = 80, DialogResult = DialogResult.Cancel };
        form.Controls.Add(box); form.Controls.Add(ok); form.Controls.Add(cancel);
        form.AcceptButton = ok; form.CancelButton = cancel;
        return form.ShowDialog() == DialogResult.OK ? box.Text.Trim() : null;
    }
#endif
}
