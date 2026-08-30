param(
    [string]$Target = "",
    [string]$Account = ""
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$AccountsPath = Join-Path $ProjectRoot "accounts.json"
$ConfigRoot = Join-Path $ProjectRoot "onekey\napcat\config"

if (-not (Test-Path $AccountsPath)) {
    throw "NapCat account manifest not found: $AccountsPath"
}

$manifest = Get-Content -Path $AccountsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$matches = @($manifest.accounts | Where-Object {
    ($Target -and $_.target -eq $Target) -or ($Account -and $_.qq -eq $Account)
})
if ($matches.Count -ne 1) {
    throw "Exactly one NapCat account must match target='$Target' account='$Account'."
}

$item = $matches[0]
$configPath = Join-Path $ConfigRoot ("onebot11_{0}.json" -f $item.qq)
if (-not (Test-Path $configPath)) {
    throw "NapCat OneBot config not found: $configPath"
}

$config = Get-Content -Path $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $config.network) {
    throw "NapCat OneBot config has no network section: $configPath"
}

$existingEndpoints = @($config.network.websocketServers) + @($config.network.websocketClients)
$existingToken = ""
foreach ($endpoint in $existingEndpoints) {
    if ($null -ne $endpoint -and $endpoint.token) {
        $existingToken = [string]$endpoint.token
        break
    }
}

if ($item.connectionMode -eq "reverse-client") {
    $client = [ordered]@{
        name = [string]$item.connectionName
        enable = $true
        url = "ws://127.0.0.1:$($item.oneBotPort)/ws"
        messagePostFormat = "array"
        reportSelfMessage = $false
        reconnectInterval = 5000
        token = $existingToken
        debug = $false
        heartInterval = 30000
    }
    $config.network.websocketServers = @()
    $config.network.websocketClients = @([pscustomobject]$client)
}
elseif ($item.connectionMode -eq "forward-server") {
    $server = [ordered]@{
        name = [string]$item.connectionName
        enable = $true
        host = "127.0.0.1"
        port = [int]$item.oneBotPort
        messagePostFormat = "array"
        reportSelfMessage = $false
        token = $existingToken
        enableForcePushEvent = $false
        debug = $false
        heartInterval = 30000
    }
    $config.network.websocketServers = @([pscustomobject]$server)
    $config.network.websocketClients = @()
}
else {
    throw "Unsupported NapCat connection mode '$($item.connectionMode)' for target '$($item.target)'."
}

$config | ConvertTo-Json -Depth 100 | Set-Content -Path $configPath -Encoding UTF8
Write-Host ("[NapCat] Configured {0} ({1}) on OneBot port {2} as {3}." -f $item.label, $item.qq, $item.oneBotPort, $item.connectionMode)
