param(
    [string]$InputPath = "..\main\main.csv",
    [string]$OutputPath = ".\scores_breakdown.csv",
    [string]$MatrixPath = ".\sorare_matrix\data\scoring_matrix_new.csv",
    [string]$RulesPath = ".\sorare_matrix\data\player_score_rules.txt",
    [string]$MappingPath = ".\sorare_matrix\data\sofascore_stat_mapping.csv"
)

$ErrorActionPreference = "Stop"

function Resolve-ScriptPath {
    param([string]$Path)

    if ([IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $PSScriptRoot $Path
}

function To-DoubleOrZero {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return 0.0
    }

    $parsed = 0.0
    if ([double]::TryParse($Value, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) {
        return $parsed
    }

    return 0.0
}

function Get-PositionKey {
    param([AllowNull()][string]$Position)

    $value = ([string]$Position).ToLowerInvariant()
    if ($value -match "goalkeeper") { return "GK" }
    if ($value -match "defender") { return "DEF" }
    if ($value -match "midfielder") { return "MID" }
    if ($value -match "forward") { return "FWD" }
    return "FWD"
}

function Get-Slug {
    param([AllowNull()][string]$Value)

    return (([string]$Value).ToLowerInvariant() -replace "[^a-z0-9]+", "_").Trim("_")
}

function Import-ScoringMatrix {
    param([string]$Path)

    $matrix = @{}
    foreach ($row in (Import-Csv -Path $Path -Encoding UTF8)) {
        $matrix[$row.Stat] = @{
            Category = $row.Category
            GK = To-DoubleOrZero $row.GK
            DEF = To-DoubleOrZero $row.DEF
            MID = To-DoubleOrZero $row.MID
            FWD = To-DoubleOrZero $row.FWD
        }
    }

    return $matrix
}

function Import-DecisiveRules {
    param([string]$Path)

    $rulesText = Get-Content -Path $Path -Raw -Encoding UTF8
    $levels = @{}
    foreach ($line in ($rulesText -split "`r?`n")) {
        if ($line -match '^(-?\d+),(\d+(?:\.\d+)?),(Yes|No)$') {
            $levels[[int]$Matches[1]] = @{
                Points = [double]::Parse($Matches[2], [Globalization.CultureInfo]::InvariantCulture)
                GuaranteedMinimum = $Matches[3] -eq "Yes"
            }
        }
    }

    if (-not $levels.ContainsKey(0)) {
        throw "Could not read decisive level 0 from $Path"
    }

    return [pscustomobject]@{
        Text = $rulesText
        Levels = $levels
    }
}

function Get-Weight {
    param(
        [hashtable]$Matrix,
        [string]$Stat,
        [string]$PositionKey
    )

    if (-not $Matrix.ContainsKey($Stat)) {
        throw "No scoring-matrix row found for stat '$Stat'"
    }

    return $Matrix[$Stat][$PositionKey]
}

function Add-PointColumn {
    param(
        $Output,
        $Row,
        [string]$OutputName,
        [string]$SourceColumn,
        [string]$MatrixStat,
        [string]$PositionKey,
        [hashtable]$Matrix
    )

    $count = To-DoubleOrZero $Row.$SourceColumn
    $weight = Get-Weight -Matrix $Matrix -Stat $MatrixStat -PositionKey $PositionKey
    $points = $count * $weight
    $Output[$OutputName] = [math]::Round($points, 4)
    $Output["weight_$((Get-Slug $MatrixStat))"] = [math]::Round($weight, 4)
    return $points
}

function Get-RowValue {
    param(
        $Row,
        [string[]]$Columns
    )

    foreach ($column in $Columns) {
        if ($Row.PSObject.Properties.Name -contains $column) {
            return To-DoubleOrZero $Row.$column
        }
    }

    return 0.0
}

function Test-Played {
    param($Row)

    $status = ([string]$Row.transfermarkt_LineupStatus).ToLowerInvariant()
    $minutes = Get-RowValue $Row @("player_sofascore_minutes_played", "transfermarkt_TMMinutesPlayed", "v3_TMMinutesPlayed")
    return $status -eq "starter" -or $minutes -gt 0
}

function Get-DecisiveLevel {
    param(
        $Row,
        [string]$PositionKey
    )

    if (-not (Test-Played $Row)) {
        return $null
    }

    $minutes = Get-RowValue $Row @("player_sofascore_minutes_played", "transfermarkt_TMMinutesPlayed", "v3_TMMinutesPlayed")
    $positiveActions =
        (Get-RowValue $Row @("player_goals", "transfermarkt_TMGoals", "v3_TMGoals")) +
        (Get-RowValue $Row @("player_goal_assist", "transfermarkt_TMAssists", "v3_TMAssists")) +
        (Get-RowValue $Row @("player_penalty_won")) +
        (Get-RowValue $Row @("player_clearance_off_line")) +
        (Get-RowValue $Row @("player_penalty_save")) +
        (Get-RowValue $Row @("player_last_man_tackle"))

    if ($PositionKey -eq "GK" -and $minutes -ge 60 -and (Get-RowValue $Row @("v3_TeamGoalsAgainst")) -eq 0) {
        $positiveActions += 1
    }

    $negativeActions =
        (Get-RowValue $Row @("v3_TMRedCards")) +
        (Get-RowValue $Row @("player_own_goals")) +
        (Get-RowValue $Row @("player_penalty_conceded")) +
        (Get-RowValue $Row @("player_error_lead_to_a_goal"))

    $level = [int]($positiveActions - $negativeActions)
    if ($level -lt -3) { return -3 }
    if ($level -gt 5) { return 5 }
    return $level
}

$InputPath = Resolve-ScriptPath $InputPath
$OutputPath = Resolve-ScriptPath $OutputPath
$MatrixPath = Resolve-ScriptPath $MatrixPath
$RulesPath = Resolve-ScriptPath $RulesPath
$MappingPath = Resolve-ScriptPath $MappingPath
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputPath) | Out-Null

$rows = Import-Csv -Path $InputPath -Encoding UTF8
if ($rows.Count -eq 0) {
    throw "No rows found in $InputPath"
}

$scoringMatrix = Import-ScoringMatrix $MatrixPath
$decisiveRules = Import-DecisiveRules $RulesPath
$statMappings = @(Import-Csv -Path $MappingPath -Encoding UTF8)
if ($statMappings.Count -eq 0) {
    throw "No stat mappings found in $MappingPath"
}

$sofascoreColumns = @(
    $rows[0].PSObject.Properties.Name |
        Where-Object { $_ -like "sofascore_*" -or $_ -like "player_*" } |
        Sort-Object
)

$outputRows = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    $positionKey = Get-PositionKey $row.Position
    $realScore = To-DoubleOrZero $row.Score
    $lineupStatus = ([string]$row.transfermarkt_LineupStatus).ToLowerInvariant()
    $canScoreActions = Test-Played $row
    $decisiveLevel = Get-DecisiveLevel $row $positionKey

    $out = [ordered]@{
        player_name = $row.Player
        club = $row.Club
        match = "$($row.sofascore_home_team) vs $($row.sofascore_away_team)"
        game_date = $row."Game Date"
        opponent = if (([string]$row.sofascore_is_home).ToLowerInvariant() -eq "true") { $row.sofascore_away_team } else { $row.sofascore_home_team }
        position = $row.Position
        lineup_status = $row.transfermarkt_LineupStatus
        sorare_score_real = $realScore
        scoring_matrix_source = $MatrixPath
        player_score_rules_source = $RulesPath
        sofascore_mapping_source = $MappingPath
    }

    foreach ($column in $sofascoreColumns) {
        $out[$column] = $row.$column
    }

    $aas = 0.0
    if ($canScoreActions) {
        foreach ($mapping in $statMappings) {
            $stat = [string]$mapping.Stat
            $pointColumn = "points_$(Get-Slug $stat)"
            $sourceColumn = [string]$mapping.SofaScoreColumn
            $out["source_$((Get-Slug $stat))"] = $sourceColumn
            $out["mapping_note_$((Get-Slug $stat))"] = $mapping.MappingNote
            $aas += Add-PointColumn -Output $out -Row $row -OutputName $pointColumn -SourceColumn $sourceColumn -MatrixStat $stat -PositionKey $positionKey -Matrix $scoringMatrix
        }
    }
    else {
        foreach ($mapping in $statMappings) {
            $stat = [string]$mapping.Stat
            $statSlug = Get-Slug $stat
            $out["source_$statSlug"] = $mapping.SofaScoreColumn
            $out["mapping_note_$statSlug"] = $mapping.MappingNote
            $out["weight_$statSlug"] = 0.0
            $out["points_$statSlug"] = 0.0
        }
    }

    $decisiveScore = if ($null -ne $decisiveLevel) {
        $decisiveRules.Levels[$decisiveLevel].Points
    }
    else {
        0.0
    }
    $decisiveGuaranteedMinimum = if ($null -ne $decisiveLevel) {
        $decisiveRules.Levels[$decisiveLevel].GuaranteedMinimum
    }
    else {
        $false
    }

    $aasUsed = if (($null -eq $decisiveLevel -or $decisiveLevel -ge 0) -and $aas -lt 0) {
        0.0
    }
    else {
        $aas
    }
    $scoreRaw = $decisiveScore + $aasUsed
    if ($decisiveGuaranteedMinimum -and $scoreRaw -lt $decisiveScore) {
        $scoreRaw = $decisiveScore
    }
    $scoreFinal = [math]::Min(100.0, [math]::Max(0.0, $scoreRaw))

    $positiveDecisiveActions =
        (Get-RowValue $row @("player_goals", "transfermarkt_TMGoals", "v3_TMGoals")) +
        (Get-RowValue $row @("player_goal_assist", "transfermarkt_TMAssists", "v3_TMAssists")) +
        (Get-RowValue $row @("player_penalty_won")) +
        (Get-RowValue $row @("player_clearance_off_line")) +
        (Get-RowValue $row @("player_penalty_save")) +
        (Get-RowValue $row @("player_last_man_tackle"))
    if ($canScoreActions -and $positionKey -eq "GK" -and (Get-RowValue $row @("player_sofascore_minutes_played", "transfermarkt_TMMinutesPlayed", "v3_TMMinutesPlayed")) -ge 60 -and (Get-RowValue $row @("v3_TeamGoalsAgainst")) -eq 0) {
        $positiveDecisiveActions += 1
    }

    $negativeDecisiveActions =
        (Get-RowValue $row @("v3_TMRedCards")) +
        (Get-RowValue $row @("player_own_goals")) +
        (Get-RowValue $row @("player_penalty_conceded")) +
        (Get-RowValue $row @("player_error_lead_to_a_goal"))

    $out["positive_decisive_actions_f"] = [math]::Round($positiveDecisiveActions, 4)
    $out["negative_decisive_actions_f"] = [math]::Round($negativeDecisiveActions, 4)
    $out["decisive_level_f"] = if ($null -ne $decisiveLevel) { $decisiveLevel } else { "" }
    $out["decisive_guaranteed_minimum_f"] = $decisiveGuaranteedMinimum
    $out["decisive_score_f"] = [math]::Round($decisiveScore, 4)
    $out["all_around_score_f"] = [math]::Round($aas, 4)
    $out["all_around_score_used_f"] = [math]::Round($aasUsed, 4)
    $out["score_f_raw"] = [math]::Round($scoreRaw, 4)
    $out["score_f"] = [math]::Round($scoreFinal, 4)
    $out["score_diff"] = [math]::Round(($scoreFinal - $realScore), 4)
    $out["score_abs_diff"] = [math]::Round([math]::Abs($scoreFinal - $realScore), 4)
    $out["formula_note"] = "Uses scoring_matrix_new.csv, sofascore_stat_mapping.csv, and player_score_rules.txt. Player-level SofaScore and lineup context are imported from the trusted SORARE V3 dataset. DNP rows receive no action score; starters and substitutes with minutes use decisive/all-around scoring."

    $outputRows.Add([pscustomobject]$out)
}

$outputRows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

$mae = (($outputRows | ForEach-Object { $_.score_abs_diff }) | Measure-Object -Average).Average
$meanReal = (($outputRows | ForEach-Object { $_.sorare_score_real }) | Measure-Object -Average).Average
$meanFormula = (($outputRows | ForEach-Object { $_.score_f }) | Measure-Object -Average).Average

Write-Host "Wrote $($outputRows.Count) rows to $OutputPath"
Write-Host "Mean real score: $([math]::Round($meanReal, 4))"
Write-Host "Mean score_f: $([math]::Round($meanFormula, 4))"
Write-Host "Mean absolute error: $([math]::Round($mae, 4))"
