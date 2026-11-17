# Shared by the Windows launchers. Selection never installs or retrains anything.
function Test-CardioPython312 {
    param([string]$Executable)
    try {
        $version = & $Executable -c "import sys; print('%s.%s' % sys.version_info[:2])" 2>$null
        return ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq '3.12')
    } catch { return $false }
}

function Resolve-CardioPython {
    param([string]$PythonPath)
    if ($PythonPath) { $candidates = @($PythonPath) }
    elseif ($env:CARDIO_PYTHON) { $candidates = @($env:CARDIO_PYTHON) }
    else {
        $candidates = @(
            (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
            (Join-Path (Split-Path $PSScriptRoot -Parent) 'tmp\cardio-runtime\Scripts\python.exe')
        )
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            if (Test-CardioPython312 $candidate) { return $candidate }
            Write-Warning "Unusable Python 3.12 environment: $candidate. Its base Python may have moved."
        }
    }
    throw 'No working project Python 3.12. Run setup.ps1 -PythonPath "C:\path\to\Python312\python.exe", or supply an existing environment with -PythonPath / CARDIO_PYTHON.'
}
