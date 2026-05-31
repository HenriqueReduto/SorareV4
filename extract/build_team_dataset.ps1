param(
    [string]$InputPath = ".\main.csv",
    [string]$OutputPath = ".\teams.csv"
)

$ErrorActionPreference = "Stop"

function To-DoubleOrNull {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    $parsed = 0.0
    if ([double]::TryParse($Value, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        return $parsed
    }

    return $null
}

function Get-Mean {
    param([double[]]$Values)

    $usable = @($Values | Where-Object { $null -ne $_ })
    if ($usable.Count -eq 0) {
        return ""
    }

    return [math]::Round((($usable | Measure-Object -Average).Average), 4)
}

function Get-StdDev {
    param([double[]]$Values)

    $usable = @($Values | Where-Object { $null -ne $_ })
    if ($usable.Count -le 1) {
        return 0.0
    }

    $mean = ($usable | Measure-Object -Average).Average
    $variance = (($usable | ForEach-Object { [math]::Pow(($_ - $mean), 2) }) | Measure-Object -Average).Average
    return [math]::Sqrt($variance)
}

function Get-EstimatedMinutes {
    param($Row)

    $status = ([string]$Row.transfermarkt_LineupStatus).ToLowerInvariant()
    if ($status -eq "starter") {
        return 90.0
    }
    if ($status -eq "bench" -or $status -eq "dnp") {
        return 0.0
    }

    return $null
}

function New-TeamSeasonAggregate {
    param(
        [string]$Team
    )

    return [pscustomobject]@{
        Team = $Team
        Season = "all"
        PlayerScores = New-Object System.Collections.Generic.List[double]
        EstimatedMinutes = New-Object System.Collections.Generic.List[double]
        Players = @{}
        Fixtures = @{}
    }
}

function New-FixtureAggregate {
    param($Row)

    return [pscustomobject]@{
        GwPoints = 0.0
        PlayerRows = 0
        Xg = To-DoubleOrNull $Row.sofascore_expected_goals_value
        Possession = To-DoubleOrNull $Row.sofascore_ball_possession_value
        TotalShots = To-DoubleOrNull $Row.sofascore_total_shots_value
        ShotsOnTarget = To-DoubleOrNull $Row.sofascore_shots_on_target_value
        CornerKicks = To-DoubleOrNull $Row.sofascore_corner_kicks_value
    }
}

$rows = Import-Csv -Path $InputPath -Encoding UTF8
if ($rows.Count -eq 0) {
    throw "No rows found in $InputPath"
}

$aggregates = @{}

foreach ($row in $rows) {
    $team = [string]$row.Club
    $teamSeasonKey = $team

    if (-not $aggregates.ContainsKey($teamSeasonKey)) {
        $aggregates[$teamSeasonKey] = New-TeamSeasonAggregate -Team $team
    }

    $aggregate = $aggregates[$teamSeasonKey]

    $score = To-DoubleOrNull $row.Score
    if ($null -ne $score) {
        $aggregate.PlayerScores.Add($score)
    }

    $minutes = Get-EstimatedMinutes $row
    if ($null -ne $minutes) {
        $aggregate.EstimatedMinutes.Add($minutes)
    }

    $playerKey = if (-not [string]::IsNullOrWhiteSpace($row."Player Slug")) {
        [string]$row."Player Slug"
    }
    else {
        [string]$row.Player
    }
    if (-not [string]::IsNullOrWhiteSpace($playerKey)) {
        $aggregate.Players[$playerKey] = $true
    }

    $fixtureKey = if (-not [string]::IsNullOrWhiteSpace($row.sofascore_event_id)) {
        "$($row.sofascore_event_id)||$($row.'Game Date')"
    }
    else {
        [string]$row."Game Date"
    }

    if (-not $aggregate.Fixtures.ContainsKey($fixtureKey)) {
        $aggregate.Fixtures[$fixtureKey] = New-FixtureAggregate $row
    }

    if ($null -ne $score) {
        $aggregate.Fixtures[$fixtureKey].GwPoints += $score
        $aggregate.Fixtures[$fixtureKey].PlayerRows += 1
    }
}

$preOutput = foreach ($aggregate in $aggregates.Values) {
    $fixtures = @($aggregate.Fixtures.Values)
    $gwPoints = [double[]]@($fixtures | ForEach-Object { [double]$_.GwPoints })
    $avgGwPoints = Get-Mean $gwPoints
    $stdDevGwPoints = Get-StdDev $gwPoints
    $consistency = if ($avgGwPoints -is [double] -and $avgGwPoints -gt 0) {
        [math]::Round((100 / (1 + ($stdDevGwPoints / $avgGwPoints))), 4)
    }
    else {
        ""
    }

    [pscustomobject]@{
        team = $aggregate.Team
        avg_gw_points = $avgGwPoints
        avg_score_per_player = Get-Mean ([double[]]@($aggregate.PlayerScores))
        clean_sheets = ""
        consistency = $consistency
        team_category = ""
        total_players = $aggregate.Players.Count
        avg_minutes = Get-Mean ([double[]]@($aggregate.EstimatedMinutes))
        avg_decisive_actions = ""
        avg_sofascore_xg = Get-Mean ([double[]]@($fixtures | ForEach-Object { $_.Xg }))
        avg_sofascore_possession = Get-Mean ([double[]]@($fixtures | ForEach-Object { $_.Possession }))
        avg_sofascore_total_shots = Get-Mean ([double[]]@($fixtures | ForEach-Object { $_.TotalShots }))
        avg_sofascore_shots_on_target = Get-Mean ([double[]]@($fixtures | ForEach-Object { $_.ShotsOnTarget }))
        avg_sofascore_corner_kicks = Get-Mean ([double[]]@($fixtures | ForEach-Object { $_.CornerKicks }))
        season = $aggregate.Season
    }
}

$ranked = @($preOutput | Sort-Object { [double]$_.avg_gw_points } -Descending)
$count = $ranked.Count
for ($index = 0; $index -lt $ranked.Count; $index += 1) {
    $percentile = if ($count -le 1) { 1.0 } else { 1.0 - ($index / ($count - 1)) }
    $ranked[$index].team_category = if ($percentile -ge 0.75) {
        "elite"
    }
    elseif ($percentile -ge 0.5) {
        "strong"
    }
    elseif ($percentile -ge 0.25) {
        "average"
    }
    else {
        "low"
    }
}

$ranked |
    Sort-Object team, season |
    Select-Object team, avg_gw_points, avg_score_per_player, clean_sheets, consistency, team_category, total_players, avg_minutes, avg_decisive_actions, avg_sofascore_xg, avg_sofascore_possession, avg_sofascore_total_shots, avg_sofascore_shots_on_target, avg_sofascore_corner_kicks, season |
    Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

Write-Host "Wrote $($ranked.Count) team-season rows to $OutputPath"
Write-Host "avg_minutes is estimated from lineup status: starter=90, bench/dnp=0"
Write-Host "clean_sheets and avg_decisive_actions are blank because main.csv has no source fields for them"
