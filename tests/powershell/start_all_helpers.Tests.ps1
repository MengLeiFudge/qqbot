$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
. (Join-Path $repoRoot "scripts/start_all_helpers.ps1")

Describe "Get-DotEnvValue" {
    It "returns the first configured key in priority order" {
        $tempPath = Join-Path $env:TEMP ("qqbot-env-" + [Guid]::NewGuid().ToString("N") + ".env")
        Set-Content -Path $tempPath -Value @(
            "QQBOT_BOT_QQ=10001",
            "QQBOT_NAPCAT_QQ=1443944862"
        )

        try {
            Get-DotEnvValue `
                -Path $tempPath `
                -Keys @("QQBOT_NAPCAT_QQ", "QQBOT_BOT_QQ") | Should Be "1443944862"
        }
        finally {
            Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
        }
    }

    It "supports quoted values" {
        $tempPath = Join-Path $env:TEMP ("qqbot-env-" + [Guid]::NewGuid().ToString("N") + ".env")
        Set-Content -Path $tempPath -Value 'QQBOT_NAPCAT_QQ="1443944862"'

        try {
            Get-DotEnvValue -Path $tempPath -Keys @("QQBOT_NAPCAT_QQ") | Should Be "1443944862"
        }
        finally {
            Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Test-ProjectBotProcessCommandLine" {
    It "recognizes the project bot when Windows resolves the venv shim to the real Python executable" {
        $root = "D:\project\qqbot"
        $commandLine = '"D:\project\qqbot\.venv\Scripts\python.exe" bot.py'
        $executablePath = "C:\Users\MLJ\AppData\Local\Python\pythoncore-3.14-64\python.exe"

        Test-ProjectBotProcessCommandLine `
            -Root $root `
            -ExecutablePath $executablePath `
            -CommandLine $commandLine | Should Be $true
    }

    It "recognizes the project bot when the full bot.py path is in the command line" {
        $root = "D:\project\qqbot"
        $commandLine = 'python.exe "D:\project\qqbot\bot.py"'

        Test-ProjectBotProcessCommandLine `
            -Root $root `
            -ExecutablePath "C:\Python314\python.exe" `
            -CommandLine $commandLine | Should Be $true
    }

    It "does not treat another project's bot.py as this project's process" {
        $root = "D:\project\qqbot"
        $commandLine = '"D:\other\qqbot\.venv\Scripts\python.exe" bot.py'

        Test-ProjectBotProcessCommandLine `
            -Root $root `
            -ExecutablePath "C:\Python314\python.exe" `
            -CommandLine $commandLine | Should Be $false
    }
}

Describe "Get-ProjectBotProcessesFromPidFile" {
    It "returns an empty list when the pid file is missing" {
        $missing = Join-Path $env:TEMP ("missing-pid-" + [Guid]::NewGuid().ToString("N") + ".txt")

        @(Get-ProjectBotProcessesFromPidFile -PidFile $missing).Count | Should Be 0
    }

    It "returns the live process id from a pid file" {
        $tempPath = Join-Path $env:TEMP ("qqbot-pid-" + [Guid]::NewGuid().ToString("N") + ".txt")
        Set-Content -Path $tempPath -Value ([string]$PID)

        try {
            $processes = @(Get-ProjectBotProcessesFromPidFile -PidFile $tempPath)

            $processes.Count | Should Be 1
            $processes[0].ProcessId | Should Be $PID
        }
        finally {
            Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Test-BotConnectedLog" {
    It "returns false when the log file is missing" {
        $missing = Join-Path $env:TEMP ("missing-" + [Guid]::NewGuid().ToString("N") + ".log")
        Test-BotConnectedLog -LogPath $missing | Should Be $false
    }

    It "returns true when OneBot reports a connected bot" {
        $tempPath = Join-Path $env:TEMP ("qqbot-connected-" + [Guid]::NewGuid().ToString("N") + ".log")
        Set-Content -Path $tempPath -Value "04-13 22:13:52 [INFO] nonebot | OneBot V11 | Bot 123456 connected"

        try {
            Test-BotConnectedLog -LogPath $tempPath | Should Be $true
        }
        finally {
            Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
        }
    }
}

Describe "Test-TcpPortEstablished" {
    It "returns true when the local port has an established connection" {
        Mock Get-NetTCPConnection {
            return [pscustomobject]@{
                LocalAddress = "127.0.0.1"
                LocalPort = 8080
                State = "Established"
            }
        }

        Test-TcpPortEstablished -HostName "127.0.0.1" -Port 8080 | Should Be $true
        Assert-MockCalled Get-NetTCPConnection -Exactly 1 -Scope It
    }

    It "returns false when no established connection exists" {
        Mock Get-NetTCPConnection {
            return $null
        }

        Test-TcpPortEstablished -HostName "127.0.0.1" -Port 8080 | Should Be $false
        Assert-MockCalled Get-NetTCPConnection -Exactly 1 -Scope It
    }
}

Describe "Wait-TcpPortClosed" {
    It "returns true when the port is already closed" {
        Mock Test-TcpPortOpen {
            return $false
        }

        Wait-TcpPortClosed -HostName "127.0.0.1" -Port 8080 -TimeoutSeconds 1 | Should Be $true
        Assert-MockCalled Test-TcpPortOpen -Exactly 1 -Scope It
    }
}

Describe "Stop-ProcessTreeFromIndex" {
    It "stops descendants first and skips duplicate descendants" {
        $script:stoppedProcessIds = @()

        Mock Stop-Process {
            param(
                [int[]]$Id
            )
            $script:stoppedProcessIds += $Id
        }

        $childrenByParentId = @{
            "100" = @(200)
            "200" = @(300)
        }
        $seen = @{}

        Stop-ProcessTreeFromIndex `
            -ProcessId 100 `
            -ChildrenByParentId $childrenByParentId `
            -Seen $seen
        Stop-ProcessTreeFromIndex `
            -ProcessId 200 `
            -ChildrenByParentId $childrenByParentId `
            -Seen $seen

        $script:stoppedProcessIds -join "," | Should Be "300,200,100"
    }
}

Describe "Stop-ProjectBotProcesses" {
    It "handles an empty child process index" {
        $script:stoppedProcessIds = @()

        Mock New-ChildProcessIndex {
            return $null
        }
        Mock Stop-Process {
            param(
                [int[]]$Id
            )
            $script:stoppedProcessIds += $Id
        }

        Stop-ProjectBotProcesses -Processes @(
            [pscustomobject]@{ ProcessId = 100 }
        )

        $script:stoppedProcessIds -join "," | Should Be "100"
    }
}
