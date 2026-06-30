from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UPDATE_ASTRBOT = ROOT / "tools" / "runtime-scripts" / "update-astrbot.ps1"
UPDATE_NAPCAT = ROOT / "tools" / "runtime-scripts" / "update-napcat.ps1"
UPDATE_ALL = ROOT / "tools" / "runtime-scripts" / "update-all.ps1"


class UpdateAstrBotContractTest(unittest.TestCase):
    def test_uv_command_is_kept_as_array_for_single_item_path_uv(self) -> None:
        script = UPDATE_ASTRBOT.read_text(encoding="utf-8-sig")

        self.assertIn("$uvCommand = @(Get-UvCommand)", script)
        self.assertIn("function Get-UvToolInstalledState", script)
        self.assertIn('$toolListCommand = @($UvCommand) + @("tool", "list", "--show-paths")', script)
        self.assertIn('Invoke-LoggedCommand (@($uvCommand) + @("tool", "upgrade", "astrbot", "--python", $PythonVersion))', script)
        self.assertIn('Invoke-LoggedCommand (@($uvCommand) + @("tool", "install", "astrbot", "--python", $PythonVersion))', script)

    def test_start_process_wrappers_do_not_pass_empty_argument_list(self) -> None:
        script = UPDATE_ASTRBOT.read_text(encoding="utf-8-sig")

        self.assertIn("function Resolve-CommandItems", script)
        self.assertIn("if ($arguments.Count -gt 0)", script)
        self.assertIn("$startArgs.ArgumentList = $arguments", script)
        self.assertNotIn("$Command[1..($Command.Count - 1)]", script)

    def test_update_all_forwards_assume_yes_to_component_scripts(self) -> None:
        script = UPDATE_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("[switch]$AssumeYes", script)
        self.assertIn('$arguments += "-AssumeYes"', script)
        self.assertIn("AssumeYes enabled; NapCat and AstrBot prompts will be auto-confirmed.", script)

    def test_update_astrbot_prompts_before_install_or_upgrade(self) -> None:
        script = UPDATE_ASTRBOT.read_text(encoding="utf-8-sig")

        self.assertIn("[switch]$AssumeYes", script)
        self.assertIn("function Confirm-AstrBotUpdate", script)
        self.assertIn("AstrBot update confirmation:", script)
        self.assertIn("Planned command:", script)
        self.assertIn("Read-Host \"Proceed with AstrBot $Action? Type Y to continue\"", script)
        self.assertIn("AstrBot update skipped by user before install or upgrade.", script)
        self.assertIn("DryRun enabled; would ask for AstrBot confirmation here.", script)
        self.assertLess(script.index("Confirm-AstrBotUpdate"), script.index("$uvCommand = @(Get-UvCommand)"))

    def test_update_napcat_skips_latest_release_before_download(self) -> None:
        script = UPDATE_NAPCAT.read_text(encoding="utf-8-sig")

        self.assertIn("[switch]$AssumeYes", script)
        self.assertIn("function Get-InstalledNapCatRelease", script)
        self.assertIn("function Get-NormalizedReleaseTag", script)
        self.assertIn("NapCat is already at latest release $version; skipping download and package replacement.", script)
        self.assertLess(script.index("NapCat is already at latest release"), script.index("Invoke-WebRequest"))

    def test_update_napcat_prompts_with_download_details_before_download(self) -> None:
        script = UPDATE_NAPCAT.read_text(encoding="utf-8-sig")

        self.assertIn("function Confirm-NapCatUpdate", script)
        self.assertIn("NapCat update confirmation:", script)
        self.assertIn("Download asset:", script)
        self.assertIn("Download URL:", script)
        self.assertIn("Download path:", script)
        self.assertIn("Account OneBot configs will be migrated after activation.", script)
        self.assertIn("Read-Host \"Proceed with NapCat download and update? Type Y to continue\"", script)
        self.assertIn("NapCat update skipped by user before download.", script)
        self.assertIn("DryRun enabled; would ask for NapCat confirmation here.", script)
        self.assertLess(script.index("Confirm-NapCatUpdate"), script.index("Invoke-WebRequest"))
        self.assertIn("function Write-NapCatReleaseMarker", script)
        self.assertIn(".qqbot-napcat-release.json", script)


if __name__ == "__main__":
    unittest.main()
