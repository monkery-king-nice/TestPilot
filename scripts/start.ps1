[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$SkipInstall,
    [switch]$NoModel,
    [string]$Database = '',
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$scriptFile = Join-Path $PSScriptRoot 'dev.py'
$launcher = @()
if ($Python) {
    $launcher = @($Python)
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $launcher = @('py', '-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $launcher = @('python')
} else {
    Write-Error 'Python 3.11+ was not found. Install Python with PATH enabled, reopen PowerShell, then retry.'
    exit 1
}

$options = @($scriptFile)
if ($Check) { $options += '--check' }
if ($SkipInstall) { $options += '--skip-install' }
if ($NoModel) { $options += '--no-model' }
if ($Database) { $options += @('--database', $Database) }
$executable = $launcher[0]
if ($launcher.Length -gt 1) { $options = @($launcher[1]) + $options }

& $executable @options
exit $LASTEXITCODE
