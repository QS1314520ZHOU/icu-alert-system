param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root "dist-output"
$imageTag = "icu-builder:cpu-universal"
$packageName = "icu-alert-system-linux-universal-$Version.tar.gz"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host "[build] cpu-universal -> $packageName" -ForegroundColor Yellow
& docker build `
    --build-arg "APP_VERSION=$Version" `
    -f (Join-Path $root "Dockerfile.universal-build") `
    -t $imageTag `
    $root
if ($LASTEXITCODE -ne 0) {
    throw "docker build failed for cpu-universal"
}

$containerId = (& docker create $imageTag).Trim()
if (-not $containerId) {
    throw "docker create failed for cpu-universal"
}

try {
    & docker cp "${containerId}:/output/$packageName" (Join-Path $outDir $packageName)
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed for cpu-universal"
    }
}
finally {
    & docker rm $containerId | Out-Null
}

Write-Host ""
Write-Host "Artifacts:" -ForegroundColor Green
Get-ChildItem -Path $outDir -Filter $packageName | Select-Object Name, Length, LastWriteTime
