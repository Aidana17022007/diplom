param(
    [string]$PythonPath,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')

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
$repairEnvironment = $false
if (Test-Path -LiteralPath $projectPython) {
    if (-not (Test-Python312 $projectPython)) {
        $existingConfig = Get-Content -LiteralPath '.venv\pyvenv.cfg' -Raw -ErrorAction SilentlyContinue
        if ($PythonPath -and (Test-Python312 $PythonPath) -and $existingConfig -match '(?m)^version\s*=\s*3\.12\.') {
            $bootstrapPython = $PythonPath
            $repairEnvironment = $true
        } else {
            throw 'The existing .venv cannot run Python 3.12. If its config records Python 3.12, rerun with -PythonPath pointing to a working 3.12 to repair its base path. For another Python version, keep .venv as a backup before creating a new environment.'
        }
    } else {
        $bootstrapPython = $projectPython
    }
} elseif ($PythonPath) {
    if (-not (Test-Python312 $PythonPath)) {
        throw 'The supplied -PythonPath must point to a working Python 3.12 executable.'
    }
    $bootstrapPython = $PythonPath
} else {
    # Reuse an existing local runtime when available; no network is needed for checks.
    try { $bootstrapPython = Resolve-CardioPython } catch {}
    $pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $bootstrapPython -and $pythonLauncher -and (Test-Python312 $pythonLauncher.Source @('-3.12'))) {
        $bootstrapPython = $pythonLauncher.Source
        $bootstrapArguments = @('-3.12')
    } elseif (-not $bootstrapPython) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($pythonCommand -and (Test-Python312 $pythonCommand.Source)) {
            $bootstrapPython = $pythonCommand.Source
        }
    }
}
if (-not $bootstrapPython) {
    throw 'Python 3.12 is required by the recorded packages. Install Python 3.12 from python.org, or run setup.ps1 -PythonPath "C:\path\to\Python312\python.exe". Python 3.14 is not compatible with the pinned NumPy version.'
}

$hasFrontend = $false
try {
    & $bootstrapPython @bootstrapArguments -c "from pathlib import Path; from scripts.verify_runtime import validate_frontend; validate_frontend(Path('frontend/dist'))" 2>$null
    $hasFrontend = $LASTEXITCODE -eq 0
} catch {}
if ($CheckOnly) {
    Write-Output "Python 3.12 selected: $bootstrapPython $bootstrapArguments"
    Write-Output "Prepared frontend present: $hasFrontend"
    if ($repairEnvironment) { throw 'The .venv needs repair. Rerun this setup command without -CheckOnly.' }
    & $bootstrapPython @bootstrapArguments -X utf8 scripts/verify_runtime.py
    if ($LASTEXITCODE -ne 0) { throw 'Runtime is incomplete. Rerun setup.ps1 without -CheckOnly.' }
    return
}

if (-not $hasFrontend) {
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Frontend build absent or incomplete. Install Node.js with npm, or use the full release archive containing frontend/dist.'
    }
    Push-Location frontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw 'Could not install frontend dependencies.' }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Could not build the frontend.' }
    } finally { Pop-Location }
    $hasFrontend = $true
}

# A working copied environment can be used immediately, without reinstalling it.
$defaultRuntime = $null
try { $defaultRuntime = Resolve-CardioPython } catch {}
if (-not $repairEnvironment -and $hasFrontend -and $bootstrapPython -eq $defaultRuntime) {
    & $bootstrapPython @bootstrapArguments -X utf8 scripts/verify_runtime.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Existing runtime is ready: $bootstrapPython"
        Write-Host 'Run START.cmd. No packages were installed.'
        return
    }
}
if ($repairEnvironment) {
    Copy-Item -LiteralPath '.venv\pyvenv.cfg' -Destination '.venv\pyvenv.cfg.before-repair' -ErrorAction SilentlyContinue
    & $bootstrapPython @bootstrapArguments -m venv --upgrade .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not repair the Python 3.12 environment.' }
} elseif (-not (Test-Path -LiteralPath $projectPython)) {
    & $bootstrapPython @bootstrapArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.12 environment.' }
}
& $projectPython -m pip install -r requirements-tested.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install the recorded Python dependencies.' }
& $projectPython -X utf8 scripts/verify_runtime.py
if ($LASTEXITCODE -ne 0) { throw 'Dependencies were installed, but runtime checks failed. See the errors above.' }
Write-Host 'Setup complete. Run START.cmd to open the local application.'
