from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qqbot.services.settings_store import SettingsStore


def test_thunder_defaults_match_old_project(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    assert store.get_thunder_config(516286670) == (0.05, 5, 20)


def test_thunder_config_is_global(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path, author_qq=605738729)

    store.set_thunder_config(516286670, 0.025, 5, 20)

    assert store.get_thunder_config(516286670) == (0.025, 5, 20)
    assert store.get_thunder_config(319567534) == (0.025, 5, 20)
