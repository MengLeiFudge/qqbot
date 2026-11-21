param(
    [Parameter(Position = 0)]
    [ValidateSet('all', 'yunqi', 'yelin', 'lanling', 'fengling')]
    [string]$Target = 'all'
)

$ErrorActionPreference = 'Stop'
& py -3 (Join-Path $PSScriptRoot 'frameworks\deploy_plugins.py') $Target
if ($LASTEXITCODE -ne 0) {
    throw "Plugin deployment failed with exit code $LASTEXITCODE."
}
