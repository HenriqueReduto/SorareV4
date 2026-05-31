param(
    [string]$MainPath = ".\main.csv",
    [string]$V3SourcePath = "C:\Users\henri\Desktop\SORARE V3\data\sorare_transfermarkt_sofascore\sorare_transfermarkt_sofascore.csv",
    [string]$OutputPath = ".\main.csv",
    [string]$BackupPath = ".\main_before_v3_player_context.csv"
)

$ErrorActionPreference = "Stop"

function Resolve-ScriptPath {
    param([string]$Path)

    if ([IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $PSScriptRoot $Path
}

function Get-DateOnlyKey {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return ([DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)).ToString("yyyy-MM-ddTHH:mm:sszzz")
}

function Get-JoinKey {
    param($Row)

    return "$($Row.Club)||$($Row.'Player Slug')||$(Get-DateOnlyKey $Row.'Game Date')"
}

function Normalize-LineupStatus {
    param([AllowNull()][string]$Value)

    $status = ([string]$Value).ToLowerInvariant()
    if ($status -match "^starter") {
        return "starter"
    }
    if ($status -match "^bench") {
        return "bench"
    }
    if ([string]::IsNullOrWhiteSpace($status)) {
        return ""
    }

    return "dnp"
}

function Set-Field {
    param(
        $Target,
        [string]$Name,
        [AllowNull()][object]$Value
    )

    if ($Target.Contains($Name)) {
        $Target[$Name] = $Value
    }
    else {
        $Target.Add($Name, $Value)
    }
}

$MainPath = Resolve-ScriptPath $MainPath
$OutputPath = Resolve-ScriptPath $OutputPath
$BackupPath = Resolve-ScriptPath $BackupPath

if (-not (Test-Path -LiteralPath $MainPath)) {
    throw "Main dataset not found: $MainPath"
}
if (-not (Test-Path -LiteralPath $V3SourcePath)) {
    throw "V3 source dataset not found: $V3SourcePath"
}

if ($OutputPath -eq $MainPath -and -not (Test-Path -LiteralPath $BackupPath)) {
    Copy-Item -LiteralPath $MainPath -Destination $BackupPath
}

$mainRows = Import-Csv -Path $MainPath -Encoding UTF8
$v3Rows = Import-Csv -Path $V3SourcePath -Encoding UTF8

$v3ByKey = @{}
$duplicateV3Keys = 0
foreach ($row in $v3Rows) {
    $key = Get-JoinKey $row
    if ([string]::IsNullOrWhiteSpace($key)) {
        continue
    }

    if ($v3ByKey.ContainsKey($key)) {
        $duplicateV3Keys += 1
        continue
    }

    $v3ByKey[$key] = $row
}

$playerStatColumns = @(
    "sofascore_event_id",
    "sofascore_event_slug",
    "sofascore_status",
    "sofascore_tournament",
    "sofascore_season",
    "sofascore_round",
    "sofascore_home_team",
    "sofascore_home_score",
    "sofascore_away_team",
    "sofascore_away_score",
    "sofascore_player_id",
    "sofascore_player_slug",
    "sofascore_shirt_number",
    "sofascore_starter",
    "sofascore_substitute",
    "sofascore_captain",
    "sofascore_stats_available",
    "sofascore_minutes_played",
    "sofascore_rating",
    "total_shots",
    "on_target_scoring_attempt",
    "shot_off_target",
    "blocked_scoring_attempt",
    "expected_goals",
    "expected_goals_on_target",
    "big_chance_missed",
    "goals",
    "goal_assist",
    "touches",
    "total_pass",
    "accurate_pass",
    "key_pass",
    "expected_assists",
    "total_long_balls",
    "accurate_long_balls",
    "total_cross",
    "accurate_cross",
    "total_contest",
    "won_contest",
    "duel_won",
    "duel_lost",
    "aerial_won",
    "aerial_lost",
    "total_tackle",
    "won_tackle",
    "interception_won",
    "total_clearance",
    "outfielder_block",
    "ball_recovery",
    "fouls",
    "was_fouled",
    "possession_lost_ctrl",
    "dispossessed",
    "unsuccessful_touch",
    "saves",
    "saved_shots_from_inside_the_box",
    "goals_prevented",
    "accurate_keeper_sweeper",
    "big_chance_created",
    "clearance_off_line",
    "error_lead_to_a_goal",
    "error_lead_to_a_shot",
    "good_high_claim",
    "last_man_tackle",
    "own_goals",
    "penalty_conceded",
    "penalty_miss",
    "penalty_save",
    "penalty_won",
    "punches",
    "cross_not_claimed"
)

$updatedRows = New-Object System.Collections.Generic.List[object]
$matchedRows = 0
$unmatchedRows = 0

foreach ($row in $mainRows) {
    $out = [ordered]@{}
    foreach ($property in $row.PSObject.Properties) {
        $out[$property.Name] = $property.Value
    }

    if (-not $out.Contains("transfermarkt_LineupStatus_original_v4")) {
        Set-Field $out "transfermarkt_LineupStatus_original_v4" $row.transfermarkt_LineupStatus
        Set-Field $out "transfermarkt_IsStarter_original_v4" $row.transfermarkt_IsStarter
        Set-Field $out "transfermarkt_IsBench_original_v4" $row.transfermarkt_IsBench
        Set-Field $out "transfermarkt_IsDnp_original_v4" $row.transfermarkt_IsDnp
        Set-Field $out "transfermarkt_TransfermarktPlayerId_original_v4" $row.transfermarkt_TransfermarktPlayerId
        Set-Field $out "transfermarkt_TransfermarktPlayerName_original_v4" $row.transfermarkt_TransfermarktPlayerName
    }

    $key = Get-JoinKey $row
    if ($v3ByKey.ContainsKey($key)) {
        $v3 = $v3ByKey[$key]
        $status = Normalize-LineupStatus $v3."Lineup Status"
        $matchedRows += 1

        Set-Field $out "v3_player_context_matched" $true
        Set-Field $out "v3_player_context_source" $V3SourcePath
        Set-Field $out "v3_LineupStatus" $v3."Lineup Status"
        Set-Field $out "v3_TMMinutesPlayed" $v3."TM Minutes Played"
        Set-Field $out "v3_TMGoals" $v3."TM Goals"
        Set-Field $out "v3_TMAssists" $v3."TM Assists"
        Set-Field $out "v3_TMYellowCards" $v3."TM Yellow Cards"
        Set-Field $out "v3_TMRedCards" $v3."TM Red Cards"
        Set-Field $out "v3_TeamGoalsFor" $v3."Team Goals For"
        Set-Field $out "v3_TeamGoalsAgainst" $v3."Team Goals Against"

        Set-Field $out "transfermarkt_LineupStatus" $status
        Set-Field $out "transfermarkt_IsStarter" ($status -eq "starter")
        Set-Field $out "transfermarkt_IsBench" ($status -eq "bench")
        Set-Field $out "transfermarkt_IsDnp" ($status -eq "dnp")
        Set-Field $out "transfermarkt_TransfermarktPlayerId" $v3.tm_player_id
        Set-Field $out "transfermarkt_TransfermarktPlayerName" $v3.tm_player_name

        foreach ($column in $playerStatColumns) {
            Set-Field $out "player_$column" $v3.$column
        }
    }
    else {
        $unmatchedRows += 1
        Set-Field $out "v3_player_context_matched" $false
    }

    $updatedRows.Add([pscustomobject]$out)
}

$updatedRows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

Write-Host "Wrote $($updatedRows.Count) rows to $OutputPath"
Write-Host "Matched V3 player context rows: $matchedRows"
Write-Host "Unmatched V3 player context rows: $unmatchedRows"
Write-Host "Duplicate V3 keys skipped: $duplicateV3Keys"
if (Test-Path -LiteralPath $BackupPath) {
    Write-Host "Backup available at $BackupPath"
}
