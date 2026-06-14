from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
START_ALL = ROOT / "scripts" / "start-all.ps1"
START_ALL_BAT = ROOT / "scripts" / "start-all.bat"
START_ASTRBOT_BAT = ROOT / "scripts" / "start-astrbot.bat"


class StartAllContractTest(unittest.TestCase):
    def test_start_all_ps1_defaults_to_astrbot_both_full(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertRegex(script, r'\[string\]\$Target\s*=\s*"astrbot"')
        self.assertIn('if ($Target -eq "astrbot")', script)
        self.assertIn('$FeatureMode = "full"', script)
        self.assertIn('$AstrBotProfile = "both"', script)
        self.assertIn('$PSBoundParameters.ContainsKey("FeatureMode")', script)
        self.assertIn('$PSBoundParameters.ContainsKey("AstrBotProfile")', script)

    def test_daily_bat_entries_start_astrbot_both_full(self) -> None:
        for path in (START_ALL_BAT, START_ASTRBOT_BAT):
            with self.subTest(path=path.name):
                content = re.sub(r"\s+", " ", path.read_text(encoding="utf-8-sig")).strip()

                self.assertIn("-Target astrbot", content)
                self.assertIn("-SkipInstall", content)
                self.assertIn("-AstrBotProfile both", content)
                self.assertIn("-FeatureMode full", content)

    def test_start_all_does_not_keep_legacy_target(self) -> None:
        content = START_ALL.read_text(encoding="utf-8-sig")
        legacy_name = "none" + "bot2"

        self.assertNotIn(legacy_name, content.lower())
        self.assertNotIn(f"napcat-{legacy_name}", content)


if __name__ == "__main__":
    unittest.main()
