param(
    [string]$SorareSofaScorePath = ".\sorare_sofascore_players.csv",
    [string]$TransfermarktPath = ".\transfermarkt\transfermarkt_lineups.csv",
    [string]$OutputPath = ".\main.csv",
    [switch]$AllowTransfermarktDateMismatch
)

$ErrorActionPreference = "Stop"

function Get-TransfermarktGameId {
    param([AllowNull()][string]$MatchKey)

    if ($MatchKey -match "game:(\d+)") {
        return $Matches[1]
    }

    return ""
}

function Get-JoinKey {
    param(
        [string]$GameId,
        [string]$EventId,
        [string]$GameDate,
        [string]$PlayerSlug
    )

    return "$EventId||$GameDate||$PlayerSlug"
}

function Get-DateOnly {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return ([DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)).UtcDateTime.ToString("yyyy-MM-dd")
}

function Get-TransfermarktCalendarDateOnly {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $date = [DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)
    try {
        $timeZone = [TimeZoneInfo]::FindSystemTimeZoneById("W. Europe Standard Time")
    }
    catch {
        try {
            $timeZone = [TimeZoneInfo]::FindSystemTimeZoneById("Europe/Berlin")
        }
        catch {
            return ""
        }
    }

    return [TimeZoneInfo]::ConvertTime($date, $timeZone).ToString("yyyy-MM-dd")
}

function Get-DateOnlyCandidates {
    param([AllowNull()][string]$Value)

    $candidates = @()
    $utcDate = Get-DateOnly $Value
    if (-not [string]::IsNullOrWhiteSpace($utcDate)) {
        $candidates += $utcDate
    }

    $transfermarktCalendarDate = Get-TransfermarktCalendarDateOnly $Value
    if (-not [string]::IsNullOrWhiteSpace($transfermarktCalendarDate)) {
        $candidates += $transfermarktCalendarDate
    }

    return @($candidates | Sort-Object -Unique)
}

$sorareRows = Import-Csv -Path $SorareSofaScorePath -Encoding UTF8
$transfermarktRows = Import-Csv -Path $TransfermarktPath -Encoding UTF8

if ($sorareRows.Count -eq 0) {
    throw "No rows found in $SorareSofaScorePath"
}

if ($transfermarktRows.Count -eq 0) {
    throw "No rows found in $TransfermarktPath"
}

$sorareColumns = @($sorareRows[0].PSObject.Properties.Name)
$transfermarktColumns = @($transfermarktRows[0].PSObject.Properties.Name)
$skipTransfermarktColumns = @(
    "Club",
    "Player",
    "PlayerSlug",
    "Position",
    "SorareScore",
    "GameDate",
    "TransfermarktGameId",
    "SofaScoreEventId",
    "HomeTeam",
    "AwayTeam",
    "IsHome",
    "Opponent"
)

$transfermarktByKey = @{}
$duplicateTransfermarktKeys = 0

foreach ($row in $transfermarktRows) {
    $key = Get-JoinKey `
        -GameId $row.TransfermarktGameId `
        -EventId $row.SofaScoreEventId `
        -GameDate $row.GameDate `
        -PlayerSlug $row.PlayerSlug

    if ($transfermarktByKey.ContainsKey($key)) {
        $duplicateTransfermarktKeys += 1
    }

    $transfermarktByKey[$key] = $row
}

$outputRows = New-Object System.Collections.Generic.List[object]
$matchedRows = 0
$unmatchedRows = 0
$dateMismatchRows = 0

foreach ($row in $sorareRows) {
    $gameId = Get-TransfermarktGameId $row.sofascore__match_key
    $key = Get-JoinKey `
        -GameId $gameId `
        -EventId $row.sofascore_event_id `
        -GameDate $row."Game Date" `
        -PlayerSlug $row."Player Slug"

    $transfermarkt = $null
    $matched = $transfermarktByKey.ContainsKey($key)

    if ($matched) {
        $transfermarkt = $transfermarktByKey[$key]

        $sorareGameDates = Get-DateOnlyCandidates $row."Game Date"
        $transfermarktMatchDate = [string]$transfermarkt.TransfermarktMatchDate
        $dateMatched = $sorareGameDates -contains $transfermarktMatchDate

        if ((-not $dateMatched) -and (-not $AllowTransfermarktDateMismatch)) {
            $matched = $false
            $dateMismatchRows += 1
        }
        else {
            $matchedRows += 1
        }
    }
    else {
        $unmatchedRows += 1
    }

    $out = [ordered]@{}

    foreach ($column in $sorareColumns) {
        $out[$column] = $row.$column
    }

    $out["transfermarkt_join_key"] = $key
    $out["transfermarkt_lineup_matched"] = $matched
    $out["transfermarkt_exact_date_matched"] = $matched

    foreach ($column in $transfermarktColumns) {
        if ($skipTransfermarktColumns -contains $column) {
            continue
        }

        $outputColumn = "transfermarkt_$column"
        if ($matched) {
            $out[$outputColumn] = $transfermarkt.$column
        }
        else {
            $out[$outputColumn] = ""
        }
    }

    $outputRows.Add([pscustomobject]$out)
}

$outputRows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8

Write-Host "Wrote $($outputRows.Count) rows to $OutputPath"
Write-Host "Transfermarkt lineup matches: $matchedRows"
Write-Host "Transfermarkt lineup unmatched: $unmatchedRows"
Write-Host "Transfermarkt date mismatches rejected: $dateMismatchRows"
Write-Host "Duplicate Transfermarkt join keys overwritten: $duplicateTransfermarktKeys"
if ($AllowTransfermarktDateMismatch) {
    Write-Host "AllowTransfermarktDateMismatch enabled: date mismatches were kept"
}
