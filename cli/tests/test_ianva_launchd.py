from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ianva_launchd_launcher_avoids_bash4_only_builtins():
    launcher = ROOT / "ianva" / "scripts" / "ianva-serve.sh"
    text = launcher.read_text()

    assert "mapfile" not in text
    assert "readarray" not in text
