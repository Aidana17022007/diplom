param(
    [string]$PythonPath,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Test-Python312 {
    param([string]$Executable, [string[]]$PrefixArguments = @())
    try {
        $version = & $Executable @PrefixArguments -c "import sys; print('%s.%s' % sys.version_info[:2])" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq '3.12')
    } catch { return $false }
}

$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$bootstrapPython = $null
$bootstrapArguments = @()
if (Test-Path -LiteralPath $projectPython) {
    if (-not (Test-Python312 $projectPython)) {
        throw 'The existing .venv must use Python 3.12. Keep it as a backup, then rerun setup.ps1 with Python 3.12.'
    }
    $bootstrapPython = $projectPython
} elseif ($PythonPath) {
    if (-not (Test-Python312 $PythonPath)) {
        throw 'The supplied -PythonPath must point to a working Python 3.12 executable.'
    }
    $bootstrapPython = $PythonPath
} else {
    $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($pythonLauncher -and (Test-Python312 $pythonLauncher.Source @('-3.12'))) {
        $bootstrapPython = $pythonLauncher.Source
        $bootstrapArguments = @('-3.12')
    } else {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand -and (Test-Python312 $pythonCommand.Source)) {
            $bootstrapPython = $pythonCommand.Source
        }
    }
}
if (-not $bootstrapPython) {
    throw 'Python 3.12 is required by the recorded packages. Install Python 3.12 from python.org, or run setup.ps1 -PythonPath "C:\path\to\Python312\python.exe". Python 3.14 is not compatible with the pinned NumPy version.'
}

$hasFrontend = Test-Path -LiteralPath (Join-Path $PSScriptRoot 'frontend\dist\index.html')
if ($CheckOnly) {
    Write-Output "Python 3.12 selected: $bootstrapPython $bootstrapArguments"
    Write-Output "Prepared frontend present: $hasFrontend"
    return
}

if (-not (Test-Path -LiteralPath $projectPython)) {
    & $bootstrapPython @bootstrapArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.12 environment.' }
}
& $projectPython -m pip install -r requirements-tested.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the recorded Python dependencies.' }
if (-not $hasFrontend) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Frontend build absent. Install Node.js with npm, or use the full release archive containing frontend/dist.'
    }
    Push-Location frontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Could not build the frontend.' }
    } finally { Pop-Location }
}
Write-Host 'Setup complete. Run START.cmd to open the local application.'
