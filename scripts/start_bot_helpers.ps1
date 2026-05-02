function Get-PyVenvConfigValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigPath,
        [Parameter(Mandatory = $true)]
        [string]$Key
    )

    if (-not (Test-Path $ConfigPath)) {
        return $null
    }

    $pattern = "^\s*" + [Regex]::Escape($Key) + "\s*=\s*(.+?)\s*$"
    foreach ($line in Get-Content $ConfigPath) {
        if ($line -match $pattern) {
            return $matches[1].Trim()
        }
    }

    return $null
}

function Invoke-VenvPythonProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath
    )

    try {
        & $PythonPath -c "import sys" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Test-VenvHealthy {
    param(
        [string]$VenvPath = ".venv"
    )

    $pythonPath = Join-Path $VenvPath "Scripts\python.exe"
    $configPath = Join-Path $VenvPath "pyvenv.cfg"
    if (-not (Test-Path $pythonPath) -or -not (Test-Path $configPath)) {
        return $false
    }

    $basePython = Get-PyVenvConfigValue -ConfigPath $configPath -Key "executable"
    if (-not $basePython) {
        $homePath = Get-PyVenvConfigValue -ConfigPath $configPath -Key "home"
        if ($homePath) {
            $basePython = Join-Path $homePath "python.exe"
        }
    }

    # Reject stale venvs whose recorded base interpreter has already been removed.
    if ($basePython -and -not (Test-Path $basePython)) {
        return $false
    }

    $probeSucceeded = Invoke-VenvPythonProbe -PythonPath $pythonPath
    return $probeSucceeded
}

function Test-PythonVersionAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    try {
        & py "-$Version" -c "import sys" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Get-PreferredPythonVersion {
    param(
        [string[]]$SupportedVersions = @("3.14", "3.12", "3.11")
    )

    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw "Cannot find the Windows Python Launcher (py.exe). Install it or create .venv manually."
    }

    foreach ($version in $SupportedVersions) {
        if (Test-PythonVersionAvailable -Version $version) {
            return $version
        }
    }

    $supportedText = $SupportedVersions -join " / "
    throw "No supported Python version was found. This launcher supports: $supportedText."
}

function New-ProjectVenv {
    param(
        [string]$VenvPath = ".venv",
        [Parameter(Mandatory = $true)]
        [string]$Version
    )

    if (Test-Path $VenvPath) {
        Remove-Item $VenvPath -Recurse -Force
    }

    & py "-$Version" -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment with Python $Version."
    }
}
