from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_inno_script_does_not_bundle_whisper_models():
    iss = (REPO_ROOT / "installer" / "AutoEditLite.iss").read_text(encoding="utf-8")

    assert "build\\models" not in iss
    assert "AutoEditLite\\models" in iss


def test_build_script_does_not_pre_download_speech_models():
    build = (REPO_ROOT / "installer" / "build.ps1").read_text(encoding="utf-8")

    assert "snapshot_download(repo_id='Systran/faster-whisper-base'" not in build
    assert "Pre-downloading faster-whisper" not in build


def test_build_script_enforces_400mb_artifact_limit():
    build = (REPO_ROOT / "installer" / "build.ps1").read_text(encoding="utf-8")

    assert "$MaxArtifactMB = 400" in build
    assert "Assert-ArtifactUnderLimit" in build
    assert "AutoEditLite-Setup.exe" in build
    assert "AutoEditLite-Portable-$Version.zip" in build


def test_build_script_stages_accuracy_measurement_tools():
    build = (REPO_ROOT / "installer" / "build.ps1").read_text(encoding="utf-8")

    assert "'accuracy_dataset.py'" in build
    assert "'output_validation.py'" in build


def test_build_script_default_version_is_valid_for_windows_version_info():
    build = (REPO_ROOT / "installer" / "build.ps1").read_text(encoding="utf-8")
    iss = (REPO_ROOT / "installer" / "AutoEditLite.iss").read_text(encoding="utf-8")

    assert "'0.1.0-dev'" not in build
    assert "'0.1.0.0'" in build
    assert '"0.1.0-dev"' not in iss
    assert '"0.1.0.0"' in iss
