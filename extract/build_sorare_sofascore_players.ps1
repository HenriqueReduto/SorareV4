param(
    [string]$SorarePath = "data\sorare\sorare_scores.csv",
    [string]$SofaScorePath = "data\sofascore\data_raw_main_sofascore_match_stats.csv",
    [string]$OutputPath = "sorare_sofascore_players.csv",
    [int]$MinTeamPlayers = 9,
    [string]$ExcludeStartDate = "2024-08-01",
    [string]$ExcludeEndDate = "2024-08-28",
    [switch]$KeepUnmatched
)

$ErrorActionPreference = "Stop"

function Normalize-Text {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $text = $Value.ToLowerInvariant()
    $transliterations = @{}
    $transliterations[[string][char]0x0131] = "i"
    $transliterations[[string][char]0x0142] = "l"
    $transliterations[[string][char]0x00F8] = "o"
    $transliterations[[string][char]0x00F0] = "d"
    $transliterations[[string][char]0x00FE] = "th"
    $transliterations[[string][char]0x0111] = "d"
    $transliterations[[string][char]0x0127] = "h"
    $transliterations[[string][char]0x00DF] = "ss"
    $transliterations[[string][char]0x00E6] = "ae"
    $transliterations[[string][char]0x0153] = "oe"

    foreach ($key in $transliterations.Keys) {
        $text = $text.Replace($key, $transliterations[$key])
    }

    $decomposed = $text.Normalize([Text.NormalizationForm]::FormD)
    $builder = [Text.StringBuilder]::new()

    foreach ($character in $decomposed.ToCharArray()) {
        $category = [Globalization.CharUnicodeInfo]::GetUnicodeCategory($character)
        if ($category -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($character)
        }
    }

    $normalized = $builder.ToString().Normalize([Text.NormalizationForm]::FormC)
    $normalized = $normalized -replace "&", " and "
    $normalized = $normalized -replace "[^a-z0-9]+", " "
    $normalized = $normalized -replace "\s+", " "
    return $normalized.Trim()
}

function Get-CanonicalPlayerName {
    param([AllowNull()][string]$Name)

    $normalized = Normalize-Text $Name

    if ($normalized -match "maximiliano.*araujo") {
        return "maximiliano araujo"
    }

    if ($normalized -match "(samu|samuel).*omorodion|aghehowa") {
        return "samu omorodion"
    }

    if ($normalized -match "(^| )trincao$|francisco.*trincao") {
        return "trincao"
    }

    return $normalized
}

$TeamAliases = @{
    "besiktas jimnastik kulubu" = "besiktas jimnastik kulubu"
    "fc porto" = "futebol clube do porto"
    "porto porto" = "futebol clube do porto"
    "futebol clube do porto" = "futebol clube do porto"
    "fc red bull salzburg" = "fussballclub red bull salzburg"
    "red bull salzburg" = "fussballclub red bull salzburg"
    "fussballclub red bull salzburg" = "fussballclub red bull salzburg"
    "fenerbahce spor kulubu" = "fenerbahce spor kulubu"
    "galatasaray spor kulubu" = "galatasaray spor kulubu"
    "sl benfica" = "sport lisboa e benfica"
    "benfica lisboa" = "sport lisboa e benfica"
    "sport lisboa e benfica" = "sport lisboa e benfica"
    "sporting braga" = "sporting clube de braga"
    "sporting clube de braga" = "sporting clube de braga"
    "sporting clube de portugal" = "sporting clube de portugal"
    "sporting cp lisboa" = "sporting clube de portugal"
    "rangers fc" = "rangers football club"
    "rangers football club" = "rangers football club"
    "celtic fc" = "the celtic football club"
    "celtic glasgow" = "the celtic football club"
    "the celtic football club" = "the celtic football club"
    "trabzonspor kulubu" = "trabzonspor kulubu"
    "vitoria guimaraes sc" = "vitoria sport clube"
    "vitoria guimaraes guimaraes" = "vitoria sport clube"
    "vitoria sport clube" = "vitoria sport clube"
}

function Get-TeamKey {
    param([AllowNull()][string]$Name)

    $normalized = Normalize-Text $Name
    if ($TeamAliases.ContainsKey($normalized)) {
        return $TeamAliases[$normalized]
    }

    return $normalized
}

function Get-SofaScoreTeamKey {
    param($Row)

    $matchKey = [string]$Row."_match_key"
    if ($matchKey -match "\|team:(.+)$") {
        return Get-TeamKey $Matches[1]
    }

    return ""
}

function Get-DateValue {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return [DateTimeOffset]::MinValue
    }

    return [DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
}

function Test-IsExcludedSorareDate {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }

    $date = (Get-DateValue $Value).UtcDateTime.Date
    $start = ([DateTime]::ParseExact($ExcludeStartDate, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)).Date
    $end = ([DateTime]::ParseExact($ExcludeEndDate, "yyyy-MM-dd", [Globalization.CultureInfo]::InvariantCulture)).Date
    return ($date -ge $start -and $date -le $end)
}

$sorareRows = Import-Csv -Path $SorarePath -Encoding UTF8
$sofaRows = Import-Csv -Path $SofaScorePath -Encoding UTF8

if ($sorareRows.Count -eq 0) {
    throw "No Sorare rows found at $SorarePath"
}

if ($sofaRows.Count -eq 0) {
    throw "No SofaScore rows found at $SofaScorePath"
}

$sorareColumns = @($sorareRows[0].PSObject.Properties.Name)
$sofaColumns = @($sofaRows[0].PSObject.Properties.Name)

$fixtureBuckets = @{}

foreach ($row in $sorareRows) {
    $playerNormalized = Normalize-Text $row.Player
    $playerCanonical = Get-CanonicalPlayerName $row.Player
    $teamKey = Get-TeamKey $row.Club
    $gameDate = [string]$row."Game Date"
    $isExcludedDate = Test-IsExcludedSorareDate $gameDate
    $bucketKey = "$teamKey||$gameDate"

    Add-Member -InputObject $row -MemberType NoteProperty -Name "_player_normalized" -Value $playerNormalized
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_player_canonical" -Value $playerCanonical
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_team_key" -Value $teamKey
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_fixture_bucket_key" -Value $bucketKey
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_excluded_missing_sofascore_date" -Value $isExcludedDate

    if ($isExcludedDate) {
        continue
    }

    if (-not $fixtureBuckets.ContainsKey($bucketKey)) {
        $fixtureBuckets[$bucketKey] = [ordered]@{
            BucketKey = $bucketKey
            TeamKey = $teamKey
            GameDate = $gameDate
            ParsedDate = Get-DateValue $gameDate
            Rows = [System.Collections.Generic.List[object]]::new()
        }
    }

    $fixtureBuckets[$bucketKey].Rows.Add($row)
}

$eligibleFixtures = New-Object System.Collections.Generic.List[object]

foreach ($fixture in $fixtureBuckets.Values) {
    $playerCount = $fixture.Rows.Count
    if ($playerCount -ge $MinTeamPlayers) {
        $eligibleFixtures.Add([pscustomobject]@{
            BucketKey = $fixture.BucketKey
            TeamKey = $fixture.TeamKey
            GameDate = $fixture.GameDate
            ParsedDate = $fixture.ParsedDate
            PlayerCount = $playerCount
            MatchRank = 0
        })
    }
}

$fixtureByBucket = @{}

foreach ($teamGroup in ($eligibleFixtures | Group-Object TeamKey)) {
    $rank = 0
    $orderedFixtures = $teamGroup.Group | Sort-Object `
        @{ Expression = { $_.ParsedDate.UtcDateTime }; Descending = $true }, `
        @{ Expression = { $_.GameDate }; Descending = $true }

    foreach ($fixture in $orderedFixtures) {
        $rank += 1
        $fixture.MatchRank = $rank
        $fixtureByBucket[$fixture.BucketKey] = $fixture
    }
}

$sofaByTeamRank = @{}
$sofaTeamCounters = @{}

foreach ($row in $sofaRows) {
    $teamKey = Get-SofaScoreTeamKey $row
    if ([string]::IsNullOrWhiteSpace($teamKey)) {
        continue
    }

    if (-not $sofaTeamCounters.ContainsKey($teamKey)) {
        $sofaTeamCounters[$teamKey] = 0
    }

    $sofaTeamCounters[$teamKey] += 1
    $rank = $sofaTeamCounters[$teamKey]
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_team_key" -Value $teamKey
    Add-Member -InputObject $row -MemberType NoteProperty -Name "_match_rank" -Value $rank
    $sofaByTeamRank["$teamKey||$rank"] = $row
}

$outputRows = New-Object System.Collections.Generic.List[object]
$watchPlayers = @("maximiliano araujo", "samu omorodion", "trincao")
$excludedDateRows = 0
$droppedUnmatchedRows = 0

foreach ($row in $sorareRows) {
    if ($row."_excluded_missing_sofascore_date") {
        $excludedDateRows += 1
        continue
    }

    if (-not $fixtureByBucket.ContainsKey($row."_fixture_bucket_key")) {
        continue
    }

    $fixture = $fixtureByBucket[$row."_fixture_bucket_key"]
    $joinKey = "$($fixture.TeamKey)||$($fixture.MatchRank)"
    $sofa = $null
    $matched = $sofaByTeamRank.ContainsKey($joinKey)
    if ($matched) {
        $sofa = $sofaByTeamRank[$joinKey]
        $matched = -not [string]::IsNullOrWhiteSpace([string]$sofa.event_id)
    }

    if ((-not $matched) -and (-not $KeepUnmatched)) {
        $droppedUnmatchedRows += 1
        continue
    }

    $out = [ordered]@{}
    foreach ($column in $sorareColumns) {
        $out[$column] = $row.$column
    }

    $out["sorare_player_normalized"] = $row."_player_normalized"
    $out["sorare_player_canonical"] = $row."_player_canonical"
    $out["is_watch_player"] = $watchPlayers -contains $row."_player_canonical"
    $out["sorare_team_key"] = $fixture.TeamKey
    $out["sorare_team_match_rank"] = $fixture.MatchRank
    $out["sorare_team_match_player_count"] = $fixture.PlayerCount
    $out["sofascore_join_key"] = $joinKey
    $out["sofascore_matched"] = $matched
    $out["excluded_missing_sofascore_date"] = $false
    $out["join_formula"] = "normalized team key + reverse chronological team match rank; Sorare fixture groups require at least $MinTeamPlayers players; Sorare fixtures from $ExcludeStartDate to $ExcludeEndDate are excluded because SofaScore is missing"

    foreach ($column in $sofaColumns) {
        $prefixedColumn = "sofascore_$column"
        if ($matched) {
            $out[$prefixedColumn] = $sofa.$column
        }
        else {
            $out[$prefixedColumn] = ""
        }
    }

    $outputRows.Add([pscustomobject]$out)
}

$outputRows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

$matchedCount = ($outputRows | Where-Object { $_.sofascore_matched -eq $true }).Count
$watchCount = ($outputRows | Where-Object { $_.is_watch_player -eq $true }).Count

Write-Host "Wrote $($outputRows.Count) player rows to $OutputPath"
Write-Host "Matched SofaScore rows: $matchedCount"
Write-Host "Watch-player rows (Maximiliano Araujo, Samu Omorodion, Trincao): $watchCount"
Write-Host "Minimum Sorare players per team fixture: $MinTeamPlayers"
Write-Host "Excluded Sorare fixture dates with missing SofaScore data: $ExcludeStartDate to $ExcludeEndDate"
Write-Host "Rows excluded by missing SofaScore date window: $excludedDateRows"
Write-Host "Rows dropped because no usable SofaScore match was available: $droppedUnmatchedRows"
if ($KeepUnmatched) {
    Write-Host "KeepUnmatched enabled: unmatched rows were kept for audit"
}
