$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $repoRoot "scripts/start_bot_helpers.ps1")

Describe "Test-VenvHealthy" {
    It "returns false when pyvenv.cfg points to a missing base python" {
        $tempRoot = Join-Path $env:TEMP ("qqbot-start-bot-test-" + [Guid]::NewGuid().ToString("N"))
        $venvPath = Join-Path $tempRoot ".venv"
        $scriptsPath = Join-Path $venvPath "Scripts"
        $cfgPath = Join-Path $venvPath "pyvenv.cfg"
        $pythonPath = Join-Path $scriptsPath "python.exe"

        New-Item -ItemType Directory -Path $scriptsPath -Force | Out-Null
        Set-Content -Path $cfgPath -Value @(
            "home = C:\MissingPython"
            "executable = C:\MissingPython\python.exe"
        )
        Set-Content -Path $pythonPath -Value ""

        try {
            Mock Invoke-VenvPythonProbe {
                throw "probe should not run when the base interpreter is already missing"
            }

            Test-VenvHealthy -VenvPath $venvPath | Should Be $false
            Assert-MockCalled Invoke-VenvPythonProbe -Exactly 0
        }
        finally {
            Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Get-PreferredPythonVersion" {
    It "prefers Python 3.14 when that is the available supported interpreter" {
        Mock Get-Command {
            return @{ Name = "py" }
        } -ParameterFilter { $Name -eq "py" }

        Mock Test-PythonVersionAvailable {
            param([string]$Version)
            return $Version -eq "3.14"
        }

        Get-PreferredPythonVersion -SupportedVersions @("3.14", "3.12", "3.11") | Should Be "3.14"
        Assert-MockCalled Test-PythonVersionAvailable -Exactly 1 -ParameterFilter { $Version -eq "3.14" }
    }
}
