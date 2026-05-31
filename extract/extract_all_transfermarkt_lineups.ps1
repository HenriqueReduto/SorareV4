param(
    [int]$RequestDelayMs = 250,
    [switch]$UseCacheOnly
)

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$transfermarktDir = Join-Path $projectRoot "transfermarkt"
$extractor = Join-Path $transfermarktDir "build_transfermarkt_lineups.ps1"
$inputPath = Join-Path $projectRoot "sorare_sofascore_players.csv"
$outputPath = Join-Path $transfermarktDir "transfermarkt_lineups.csv"
$fixtureMapPath = Join-Path $transfermarktDir "transfermarkt_fixture_map.csv"
$cacheDir = Join-Path $transfermarktDir "cache\lineups"

if (-not (Test-Path -LiteralPath $extractor)) {
    throw "Missing extractor script: $extractor"
}

if (-not (Test-Path -LiteralPath $inputPath)) {
    throw "Missing input CSV: $inputPath"
}

$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $extractor,
    "-InputPath", $inputPath,
    "-OutputPath", $outputPath,
    "-FixtureMapPath", $fixtureMapPath,
    "-CacheDir", $cacheDir,
    "-RequestDelayMs", $RequestDelayMs
)

if ($UseCacheOnly) {
    $arguments += "-UseCacheOnly"
}

& powershell @arguments

if ($LASTEXITCODE -ne 0) {
    throw "Transfermarkt extraction failed with exit code $LASTEXITCODE"
}
