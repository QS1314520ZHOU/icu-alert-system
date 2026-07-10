param(
    [switch]$SkipFrontendBuild,
    [switch]$SkipPyInstallerClean
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendDir = Join-Path $root "frontend"
$backendDir = Join-Path $root "backend"
$frontendDist = Join-Path $frontendDir "dist"
$backendStatic = Join-Path $backendDir "static"
$specFile = Join-Path $backendDir "icu_alert_gpu.spec"
$pyInstallerDist = Join-Path $backendDir "dist\ICU-Alert-System-GPU"
$envExample = Join-Path $backendDir ".env.example"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

Write-Host "== ICU Alert GPU EXE Build ==" -ForegroundColor Cyan
Write-Host "Root: $root"
Write-Host "Python: $pythonExe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

if (-not (Test-Path $specFile)) {
    throw "Spec file not found: $specFile"
}

if (-not $SkipFrontendBuild) {
    Write-Host "[1/4] Building frontend..." -ForegroundColor Yellow
    Push-Location $frontendDir
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
elseif (-not (Test-Path $frontendDist)) {
    throw "frontend/dist must exist when SkipFrontendBuild is used."
}

Write-Host "[2/4] Copying frontend assets to backend/static ..." -ForegroundColor Yellow
if (Test-Path $backendStatic) {
    Remove-Item -Recurse -Force $backendStatic
}
New-Item -ItemType Directory -Path $backendStatic | Out-Null
Copy-Item -Path (Join-Path $frontendDist "*") -Destination $backendStatic -Recurse -Force

Write-Host "[3/4] Checking PyInstaller ..." -ForegroundColor Yellow
& $pythonExe -m PyInstaller --version | Out-Null

Write-Host "[4/4] Building GPU EXE ..." -ForegroundColor Yellow
if (Test-Path $pyInstallerDist) {
    Write-Host "Cleaning existing GPU dist output ..." -ForegroundColor DarkYellow
    Remove-Item -Recurse -Force $pyInstallerDist
}

Push-Location $backendDir
try {
    $pyiArgs = @("-m", "PyInstaller")
    if (-not $SkipPyInstallerClean) {
        $pyiArgs += "--clean"
    }
    $pyiArgs += "-y"
    $pyiArgs += $specFile
    & $pythonExe @pyiArgs
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (Test-Path $envExample) {
    Copy-Item -Path $envExample -Destination (Join-Path $pyInstallerDist ".env.example") -Force
}

Write-Host ""
Write-Host "Build completed." -ForegroundColor Green
Write-Host "Output dir: $pyInstallerDist"
Write-Host "Executable: $(Join-Path $pyInstallerDist 'ICU-Alert-System-GPU.exe')"
