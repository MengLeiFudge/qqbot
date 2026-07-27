from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = ROOT / "scripts"
START_ALL = ROOT / "tools" / "runtime-scripts" / "start-all.ps1"
START_ASTRBOT = ROOT / "tools" / "runtime-scripts" / "start-astrbot.ps1"
ENSURE_NAPCAT_BUILTIN = ROOT / "tools" / "runtime-scripts" / "ensure-napcat-builtin-plugin.ps1"
START_ALL_BAT = ROOT / "scripts" / "start-all.bat"


class StartAllContractTest(unittest.TestCase):
    def test_start_all_ps1_defaults_to_astrbot_both_full(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertRegex(script, r'\[string\]\$Target\s*=\s*"astrbot"')
        self.assertIn("[int]$AstrBotOneBotPort = 6201", script)
        self.assertIn("[int]$AstrBotAngelOneBotPort = 6200", script)
        self.assertIn("[switch]$UseChildWindows", script)
        self.assertIn("[switch]$ForceRestart", script)
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
        self.assertIn("AstrBot preflight:", script)
        self.assertIn("AstrBot launch mode:", script)
        self.assertIn("AstrBot Core lifecycle started", script)
        self.assertIn("AstrBot loading plugin:", script)
        self.assertIn("AstrBot loading provider:", script)
        self.assertIn("AstrBot default provider selected:", script)
        self.assertIn("AstrBot knowledge base initialized", script)
        self.assertIn("AstrBot WebUI starting:", script)
        self.assertIn("AstrBot server listening on port", script)
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
        for path in (START_ALL, START_ASTRBOT, ENSURE_NAPCAT_BUILTIN):
            script = path.read_text(encoding="utf-8-sig")

            self.assertIsNone(re.search(r"[\u4e00-\u9fff]", script), path.name)

    def test_start_all_ensures_napcat_builtin_plugin_before_napcat_start(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Ensure-NapCatBuiltinPlugin", script)
        self.assertIn("ensure-napcat-builtin-plugin.ps1", script)
        self.assertIn("NapCat builtin plugin ensure failed", script)
        self.assertIn("Ensure-NapCatBuiltinPlugin -LogFile $launcherLog -ConsolePrefix $consolePrefix", script)
        self.assertLess(
            script.index("Ensure-NapCatBuiltinPlugin -LogFile $launcherLog -ConsolePrefix $consolePrefix"),
            script.index("Sync-NapCatOneBotClientConfig -Account $Account"),
        )

        ensure_script = ENSURE_NAPCAT_BUILTIN.read_text(encoding="utf-8-sig")
        self.assertIn("https://github.com/NapNeko/napcat-plugin-index/releases/download/v1.0.0/napcat-plugin-builtin.zip", ensure_script)
        self.assertIn("napcat-plugin-builtin", ensure_script)
        self.assertIn("prefix:\\s*\"#napcat\"", ensure_script)
        self.assertIn("plugin_onmessage", ensure_script)
        self.assertIn("config\\plugins.json", ensure_script)
        self.assertIn("Ensure-NapCatBuiltinPluginEnabled", ensure_script)
        self.assertIn("NapCat builtin plugin enabled in:", ensure_script)
        self.assertIn("Write-Utf8NoBomText", ensure_script)
        self.assertIn("NapCat plugin status config rewritten without UTF-8 BOM", ensure_script)

    def test_force_restart_stops_workspace_napcat_process_tree_before_starting_accounts(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Stop-NapCatWorkspaceProcesses", script)
        self.assertIn("launcher-user\\.bat", script)
        self.assertIn("NapCatWinBootMain\\.exe", script)
        self.assertIn('Stop-NapCatWorkspaceProcesses -Reason "force restart"', script)
        self.assertLess(
            script.index('Stop-NapCatWorkspaceProcesses -Reason "force restart"'),
            script.index("Starting NapCat accounts:"),
        )

    def test_start_all_uses_quick_login_markers_for_dual_napcat_startup(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Get-NapCatLoginMarkerPath", script)
        self.assertIn("function Test-NapCatQuickLoginReady", script)
        self.assertIn("function Set-NapCatQuickLoginReady", script)
        self.assertIn("function Test-AllNapCatQuickLoginReady", script)
        self.assertIn("NapCat quick-login markers are complete; starting accounts in parallel.", script)
        self.assertIn("starting accounts serially to protect shared QR image", script)
        self.assertIn("Waiting for NapCat account startup before launching the next account", script)
        self.assertIn('Complete-ChildStage -RunId $RunId -Component "astrbot" -Stage "ports-ready"', script)
        self.assertIn('Wait-ChildStages -RunId $runId -Components $startBotComponents -Stage "ports-ready"', script)
        self.assertIn("Waiting for bot ports before starting NapCat accounts.", script)
        self.assertLess(
            script.index('Wait-ChildStages -RunId $runId -Components $startBotComponents -Stage "ports-ready"'),
            script.index("Starting NapCat accounts:"),
        )
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
        self.assertIn("function Write-StartupPhase", script)
        self.assertIn("AstrBot startup phase [{0}]: {1}", script)
        self.assertIn('Get-Date -Format "HH:mm:ss.fff"', script)
        self.assertIn('Write-StartupPhase "sync profile config begin"', script)
        self.assertIn('Write-StartupPhase "sync profile config done"', script)
        self.assertIn('Write-StartupPhase "sync local plugins begin"', script)
        self.assertIn('Write-StartupPhase "sync local plugins done"', script)
        self.assertIn('Write-StartupPhase "environment configured"', script)
        self.assertIn('Write-StartupPhase "invoke astrbot run"', script)

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
        self.assertIn("NoPauseOnFailure = `$true", script)
        self.assertIn("function Start-IsolatedProcess", script)
        self.assertIn("$startInfo.UseShellExecute = $true", script)
        self.assertIn('$launchCommand = Join-Path $launchRoot "$LaunchName.cmd"', script)
        self.assertIn('Set-Content -Path $pidLiteral -Value `$PID -Encoding ASCII', script)
        self.assertIn('1>> "$StdoutLog" 2>> "$StderrLog"', script)
        self.assertNotIn("1>> $stdoutLiteral", script)
        self.assertIn('`$childParameters = @{', script)
        self.assertIn("@childParameters", script)
        self.assertNotIn("@childArguments", script)
        self.assertIn('-LaunchName "supervisor_launcher"', script)
        self.assertIn('-LaunchName "background_launcher"', script)
        self.assertNotIn("-RedirectStandardOutput", script)
        self.assertNotIn("-RedirectStandardError", script)
        self.assertIn("supervisor_stdout.log", script)
        self.assertIn("supervisor_stderr.log", script)
        self.assertIn("Flush-ComponentsLauncherLogs", script)
        self.assertIn("function Stop-BackgroundWrapperProcess", script)
        self.assertIn("Stopping $Name wrapper pid=$($Process.Id) after readiness was confirmed.", script)
        self.assertIn('Stop-BackgroundWrapperProcess -Process $process -Name "AstrBot background launcher"', script)
        self.assertIn("Stop-BackgroundWrapperProcess -Process $process -Name \"NapCat account $Account background launcher\"", script)

    def test_start_all_exits_without_waiting_for_runtime_log_handles(self) -> None:
        """Completed launchers must not wait on pipes inherited by runtime grandchildren."""
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Exit-LauncherProcess", script)
        self.assertIn("Runtime grandchildren can inherit redirected handles", script)
        self.assertIn("[System.Environment]::Exit($ExitCode)", script)
        self.assertGreaterEqual(script.count("Exit-LauncherProcess -ExitCode 0"), 2)
        self.assertGreaterEqual(script.count("Exit-LauncherProcess -ExitCode 1"), 2)
        self.assertNotRegex(script, r"(?m)^\s*exit\s+[01]\s*$")

    def test_start_all_reuses_existing_ready_runtime_by_default(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("function Get-MissingAstrBotReadyPorts", script)
        self.assertIn("function Get-MissingNapCatConnectionComponents", script)
        self.assertIn("function Test-EstablishedTcpConnection", script)
        self.assertIn("Startup mode: ensure running; existing ready runtime will be reused.", script)
        self.assertIn("Startup mode: force restart.", script)
        self.assertIn("Existing AstrBot ports and NapCat connections are ready; reusing current runtime.", script)
        self.assertIn("Bot services already ready; AstrBot will not be restarted.", script)
        self.assertIn("Using existing bot ports before starting NapCat accounts.", script)
        self.assertIn("Write-ExistingRuntimeDiagnostics", script)
        self.assertIn("$startBotComponents = @()", script)
        self.assertIn("$startNapCatComponents = @($missingNapCatComponents)", script)
        self.assertLess(
            script.index("Startup mode: ensure running; existing ready runtime will be reused."),
            script.index("Starting bot services:"),
        )

    def test_start_all_writes_structured_child_failure_details(self) -> None:
        script = START_ALL.read_text(encoding="utf-8-sig")

        self.assertIn("Logging must never abort startup", script)
        self.assertIn("[object]$ErrorRecord = $null", script)
        self.assertIn("fully_qualified_error_id=", script)
        self.assertIn("$ErrorRecord.InvocationInfo.ScriptLineNumber", script)
        self.assertIn("$ErrorRecord.ScriptStackTrace", script)
        self.assertIn("Failure detail: type=$errorType id=$errorId", script)
        self.assertIn("Failure stack:", script)
        self.assertIn("Fail-Child -RunId $RunId -Component $Component -Message $message -ErrorRecord $_", script)
        self.assertIn("Select-Object -First 1", script)


if __name__ == "__main__":
    unittest.main()
