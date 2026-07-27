import os
import subprocess
import tarfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_SCRIPT = PROJECT_ROOT / "install.sh"


def _build_archive(tmp_path: Path, *, include_nested_installer: bool) -> Path:
    archive_root = tmp_path / "Clowraider-trh-test"
    scripts_dir = archive_root / "scripts"
    scripts_dir.mkdir(parents=True)

    if include_nested_installer:
        (scripts_dir / "install.sh").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "printf '%s\\n' \"$PWD\" > \"$BOOTSTRAP_TEST_OUTPUT_DIR/pwd.txt\"\n"
            "printf '%s\\n' \"$@\" > \"$BOOTSTRAP_TEST_OUTPUT_DIR/args.txt\"\n",
            encoding="utf-8",
        )

    archive_path = tmp_path / "trh.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(archive_root, arcname=archive_root.name)

    return archive_path


def test_bootstrap_downloads_archive_and_forwards_arguments(tmp_path):
    archive_path = _build_archive(tmp_path, include_nested_installer=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    env = os.environ.copy()
    env["TRH_BOOTSTRAP_ARCHIVE_URL"] = archive_path.as_uri()
    env["BOOTSTRAP_TEST_OUTPUT_DIR"] = str(output_dir)

    result = subprocess.run(
        ["sh", str(BOOTSTRAP_SCRIPT), "--dry-run", "two words"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Downloading TRH archive from GitHub" in result.stdout
    assert "Running scripts/install.sh" in result.stdout
    assert (output_dir / "args.txt").read_text(encoding="utf-8").splitlines() == [
        "--dry-run",
        "two words",
    ]
    assert Path((output_dir / "pwd.txt").read_text(encoding="utf-8").strip()).name == "Clowraider-trh-test"


def test_bootstrap_fails_clearly_when_nested_installer_is_missing(tmp_path):
    archive_path = _build_archive(tmp_path, include_nested_installer=False)

    env = os.environ.copy()
    env["TRH_BOOTSTRAP_ARCHIVE_URL"] = archive_path.as_uri()

    result = subprocess.run(
        ["sh", str(BOOTSTRAP_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Expected installer script not found: scripts/install.sh" in result.stderr
