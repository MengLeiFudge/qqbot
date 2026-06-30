from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ROOT / "scripts"
START_ALL = ROOT / "tools" / "runtime-scripts" / "start-all.ps1"
START_ASTRBOT = ROOT / "tools" / "runtime-scripts" / "start-astrbot.ps1"
START_ALL_BAT = ROOT / "scripts" / "start-all.bat"


class StartAllContractTest(unittest.TestCase):
    def test_start_all_ps1_defaults_to_astrbot_both_full(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertRegex(script, r'\[string\]\$Target\s*=\s*"astrbot"')
        self.assertIn("[int]$AstrBotOneBotPort = 6201", script)
        self.assertIn("[int]$AstrBotAngelOneBotPort = 6200", script)
        self.assertIn("[switch]$UseChildWindows", script)
        self.assertIn('if ($Target -eq "astrbot")', script)
        self.assertIn('$FeatureMode = "full"', script)
        self.assertIn('$AstrBotProfile = "both"', script)
        self.assertIn('$PSBoundParameters.ContainsKey("FeatureMode")', script)
        self.assertIn('$PSBoundParameters.ContainsKey("AstrBotProfile")', script)

    def test_scripts_directory_only_exposes_all_bat_entries(self) -> None:
        script_files = {path.name for path in SCRIPTS_ROOT.iterdir() if path.is_file()}

        self.assertEqual(script_files, {"start-all.bat", "update-all.bat"})

    def test_daily_bat_entry_starts_astrbot_both_full(self) -> None:
        content = re.sub(r"\s+", " ", START_ALL_BAT.read_text(encoding="utf-8-sig")).strip()

        self.assertIn(r"tools\runtime-scripts\start-all.ps1", content)
        self.assertIn("-Target astrbot", content)
        self.assertIn("-SkipInstall", content)
        self.assertIn("-AstrBotProfile both", content)
        self.assertIn("-FeatureMode full", content)
        self.assertIn("Press any key to close this window . . .", content)
        self.assertIn("pause >nul", content)
        self.assertIn("exit /b %START_ALL_EXIT_CODE%", content)

    def test_start_all_does_not_keep_legacy_target(self) -> None:
        content = START_ALL.read_text(encoding="utf-8-sig")
        legacy_name = "none" + "bot2"

        self.assertNotIn(legacy_name, content.lower())
        self.assertNotIn(f"napcat-{legacy_name}", content)

    def test_start_all_reports_wait_diagnostics(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Get-StartupLogSignalSummary", script)
        self.assertIn("function Get-SafeConsoleLogTailText", script)
        self.assertIn("function Test-AsciiText", script)
        self.assertIn("function Write-WaitDiagnostic", script)
        self.assertIn("Still waiting for established TCP connection", script)
        self.assertIn("Final status before timeout waiting for established TCP connection", script)
        self.assertIn("NapCat quick login failed; waiting for QR login", script)
        self.assertIn("NapCat is waiting for QR scan authorization", script)
        self.assertIn("NapCat is waiting for QR login; shared QR image path detected", script)
        self.assertIn("QR image saved:", script)
        self.assertIn("latest ascii log:", script)
        self.assertIn("Recent log only contains non-ASCII text; open the log file directly.", script)
        self.assertIn("Get-TcpPortDiagnostic -Port $Port", script)
        self.assertIn("-StatusLogFile $stdoutLog", script)
        self.assertIn("-Port $BotPort -TimeoutSeconds 300", script)

    def test_start_all_logs_napcat_client_config_target(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("Updated NapCat OneBot client config", script)
        self.assertIn("NapCat OneBot client config already matches target", script)
        self.assertIn("account=$Account client=$($client.name) url=$targetUrl enable=True", script)
        self.assertIn("Sync-NapCatOneBotClientConfig -Account $Account", script)
        self.assertIn("-LogFile $launcherLog", script)

    def test_runtime_start_scripts_keep_console_text_ascii(self) -> None:
        for path in (START_ALL, START_ASTRBOT):
            script = path.read_text(encoding="utf-8-sig")

            self.assertIsNone(re.search(r"[\u4e00-\u9fff]", script), path.name)

    def test_start_all_uses_quick_login_markers_for_dual_napcat_startup(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Get-NapCatLoginMarkerPath", script)
        self.assertIn("function Test-NapCatQuickLoginReady", script)
        self.assertIn("function Set-NapCatQuickLoginReady", script)
        self.assertIn("function Test-AllNapCatQuickLoginReady", script)
        self.assertIn("NapCat quick-login markers are complete; starting accounts in parallel.", script)
        self.assertIn("starting accounts serially to protect shared QR image", script)
        self.assertIn("Waiting for NapCat account startup before launching the next account", script)
        self.assertIn("Wait-Children -RunId $runId -Components @($componentName)", script)
        self.assertIn('Set-NapCatQuickLoginReady -Account $Account -Ready $true -Reason "established-connection"', script)
        self.assertIn('Set-NapCatQuickLoginReady -Account $Account -Ready $false -Reason "connection-timeout"', script)
        self.assertIn('Set-NapCatQuickLoginReady -Account $account -Ready $false -Reason "child-failed"', script)
        self.assertIn("$startedNapCatInParallel = $true", script)
        self.assertLess(
            script.index('$napcatComponents += "napcat-astrbot-angel"'),
            script.index('$napcatComponents += "napcat-astrbot-demon"'),
        )

    def test_start_astrbot_reports_launch_mode(self) -> None:
        script = START_ASTRBOT.read_text(encoding="utf-8-sig")

        self.assertIn("[int]$AiocqhttpPort = 6201", script)
        self.assertIn("[int]$AngelAiocqhttpPort = 6200", script)
        self.assertIn("AstrBot launch mode: direct uv tool executable", script)
        self.assertIn("AstrBot launch mode: PATH astrbot command", script)
        self.assertIn("[switch]$AllowUvToolRun", script)
        self.assertIn("AstrBot launch mode: uv tool run", script)
        self.assertIn("Run scripts\\update-all.bat first", script)
        self.assertIn("To bootstrap from PyPI during startup, rerun with -AllowUvToolRun", script)

    def test_start_all_defaults_to_single_terminal_with_component_prefixes(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("Display mode: single terminal with component prefixes.", script)
        self.assertIn("Display mode: child windows.", script)
        self.assertIn("function Get-ComponentConsolePrefix", script)
        self.assertIn('"astrbot" { return "[AstrBot]" }', script)
        self.assertIn('"napcat-astrbot-angel" { return "[NapCat] [Angel]" }', script)
        self.assertIn('"napcat-astrbot-demon" { return "[NapCat] [Demon]" }', script)
        self.assertIn("[Launcher]", script)
        self.assertIn("Start-ChildProcess", script)
        self.assertIn("-NoPauseOnFailure", script)
        self.assertIn("supervisor_stdout.log", script)
        self.assertIn("supervisor_stderr.log", script)
        self.assertIn("Flush-ComponentsLauncherLogs", script)


if __name__ == "__main__":
    unittest.main()
