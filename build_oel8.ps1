param(
    [string]$Version = "1.0.0",
    [ValidateSet("cpu", "gpu", "both")]
    [string]$Variant = "both"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root "dist-output"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Build-Variant {
    param([string]$BuildVariant)

    $imageTag = "icu-builder:$BuildVariant"
    $packageName = "icu-alert-system-$BuildVariant-$Version.el8.x86_64.tar.gz"

    Write-Host "[build] $BuildVariant -> $packageName" -ForegroundColor Yellow
    & docker build `
        --build-arg "BUILD_VARIANT=$BuildVariant" `
        --build-arg "APP_VERSION=$Version" `
        -f (Join-Path $root "Dockerfile.build") `
        -t $imageTag `
        $root
    if ($LASTEXITCODE -ne 0) {
        throw "docker build failed for variant: $BuildVariant"
    }

    $containerId = (& docker create $imageTag).Trim()
    if (-not $containerId) {
        throw "docker create failed for variant: $BuildVariant"
    }

    try {
        & docker cp "${containerId}:/output/$packageName" (Join-Path $outDir $packageName)
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed for variant: $BuildVariant"
        }
    }
    finally {
        & docker rm $containerId | Out-Null
    }
}

if ($Variant -eq "both") {
    Build-Variant "cpu"
    Build-Variant "gpu"
}
else {
    Build-Variant $Variant
}

Write-Host ""
Write-Host "Artifacts:" -ForegroundColor Green
Get-ChildItem -Path $outDir -Filter "*.tar.gz" | Select-Object Name, Length, LastWriteTime
