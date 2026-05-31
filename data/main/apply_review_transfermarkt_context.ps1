param(
    [string]$MainPath = ".\main.csv",
    [string]$SorareScoresPath = "..\sorare\sorare_scores.csv",
    [string]$TransfermarktSquadsPath = "..\transfermarkt\club_matchday_squads.csv",
    [string]$ReviewWorkbookPath = "..\player_ids\sorare_transfermarkt_player_matches_review.xlsx",
    [string]$ManualCorrectionsPath = "..\player_ids\sorare_transfermarkt_player_manual_corrections.csv",
    [string]$CombinedOutputPath = ".\sorare_scores_transfermarkt_context.csv",
    [string]$OutputMainPath = ".\main.csv",
    [string]$BackupPath = ".\main_before_review_transfermarkt_context.csv"
)

$ErrorActionPreference = "Stop"

function Resolve-ScriptPath {
    param([string]$Path)

    if ([IO.Path]::IsPathRooted($Path)) {
        return $Path
    }

    return Join-Path $PSScriptRoot $Path
}

function Read-XlsxSheet {
    param(
        [string]$Path,
        [int]$SheetNumber
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $stream = [IO.File]::Open((Resolve-Path $Path), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $zip = New-Object IO.Compression.ZipArchive($stream, [IO.Compression.ZipArchiveMode]::Read, $false)
    try {
        [xml]$sharedXml = (New-Object IO.StreamReader($zip.GetEntry("xl/sharedStrings.xml").Open())).ReadToEnd()
        $sharedNs = New-Object Xml.XmlNamespaceManager($sharedXml.NameTable)
        $sharedNs.AddNamespace("x", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")

        $sharedStrings = New-Object System.Collections.Generic.List[string]
        foreach ($si in $sharedXml.SelectNodes("//x:si", $sharedNs)) {
            $text = ($si.SelectNodes(".//x:t", $sharedNs) | ForEach-Object { $_.InnerText }) -join ""
            $sharedStrings.Add($text)
        }

        function Get-ColIndex {
            param([string]$CellRef)

            $letters = $CellRef -replace "[0-9]", ""
            $index = 0
            foreach ($ch in $letters.ToCharArray()) {
                $index = ($index * 26) + ([int][char]$ch - [int][char]"A" + 1)
            }

            return $index - 1
        }

        function Get-CellText {
            param($Cell)

            if ($null -eq $Cell.v) {
                return ""
            }

            if ($Cell.t -eq "s") {
                return $sharedStrings[[int]$Cell.v]
            }

            return [string]$Cell.v
        }

        [xml]$sheetXml = (New-Object IO.StreamReader($zip.GetEntry("xl/worksheets/sheet$SheetNumber.xml").Open())).ReadToEnd()
        $sheetNs = New-Object Xml.XmlNamespaceManager($sheetXml.NameTable)
        $sheetNs.AddNamespace("x", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")

        $headers = $null
        $objects = New-Object System.Collections.Generic.List[object]
        foreach ($row in $sheetXml.SelectNodes("//x:sheetData/x:row", $sheetNs)) {
            $values = @{}
            foreach ($cell in $row.SelectNodes("x:c", $sheetNs)) {
                $values[(Get-ColIndex $cell.r)] = Get-CellText $cell
            }

            if ($null -eq $headers) {
                $maxIndex = ($values.Keys | Measure-Object -Maximum).Maximum
                $headers = for ($i = 0; $i -le $maxIndex; $i++) { $values[$i] }
                continue
            }

            $object = [ordered]@{}
            for ($i = 0; $i -lt $headers.Count; $i++) {
                $object[$headers[$i]] = if ($values.ContainsKey($i)) { $values[$i] } else { "" }
            }
            $objects.Add([pscustomobject]$object)
        }

        return $objects
    }
    finally {
        $zip.Dispose()
        $stream.Dispose()
    }
}

function Get-DateKey {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return ([DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture)).ToString("yyyy-MM-dd")
}

function Normalize-Name {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $normalized = $Value.Normalize([Text.NormalizationForm]::FormD)
    $chars = New-Object System.Collections.Generic.List[char]
    foreach ($char in $normalized.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($char) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            $chars.Add($char)
        }
    }

    $plain = -join $chars
    return (($plain.ToLowerInvariant() -replace "[^a-z0-9]+", " ") -replace "\s+", " ").Trim()
}

function Get-EffectiveReviewValue {
    param(
        $Row,
        [string]$ManualColumn,
        [string]$AutoColumn
    )

    if (-not [string]::IsNullOrWhiteSpace($Row.$ManualColumn)) {
        return $Row.$ManualColumn
    }

    return $Row.$AutoColumn
}

function Get-SorarePlayerKey {
    param($Row)

    return "$(($Row.'Club Slug').ToLowerInvariant())||$($Row.'Player Slug')"
}

function Get-FallbackPlayerKey {
    param($Row)

    return "$(($Row.'Club Slug').ToLowerInvariant())||$(Normalize-Name $Row.Player)"
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

function Get-CombinedStatus {
    param([AllowNull()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "DNP"
    }

    $lower = $Value.ToLowerInvariant()
    if ($lower -eq "starter" -or $lower -eq "starting_lineup") {
        return "Starter"
    }
    if ($lower -eq "bench" -or $lower -eq "substitutes") {
        return "Bench"
    }

    return "DNP"
}

function Get-MainStatus {
    param([AllowNull()][string]$Value)

    return (Get-CombinedStatus $Value).ToLowerInvariant()
}

function Get-MatchContext {
    param($SorareRow)

    $dateKey = Get-DateKey $SorareRow.'Game Date'
    $review = $reviewBySorareKey[(Get-SorarePlayerKey $SorareRow)]
    if ($null -eq $review) {
        $review = $reviewByFallbackKey[(Get-FallbackPlayerKey $SorareRow)]
    }

    $tmRow = $null
    $tmPlayerId = ""
    $tmPlayerName = ""

    if ($null -ne $review) {
        $tmPlayerId = $review.tm_player_id
        $tmPlayerName = $review.tm_player_name
        if (-not [string]::IsNullOrWhiteSpace($tmPlayerId)) {
            $tmRow = $tmSquadsByPlayerIdAndDate["$tmPlayerId||$dateKey"]
        }
        if ($null -eq $tmRow -and -not [string]::IsNullOrWhiteSpace($tmPlayerName)) {
            $tmRow = $tmSquadsByNameClubAndDate["$(Normalize-Name $tmPlayerName)||$(($SorareRow.'Club Slug').ToLowerInvariant())||$dateKey"]
        }
    }

    if ($null -eq $tmRow) {
        $tmRow = $tmSquadsByNameClubAndDate["$(Normalize-Name $SorareRow.Player)||$(($SorareRow.'Club Slug').ToLowerInvariant())||$dateKey"]
        if ($null -ne $tmRow) {
            $tmPlayerId = $tmRow.tm_player_id
            $tmPlayerName = $tmRow.tm_player_name
        }
    }

    return [pscustomobject]@{
        Review = $review
        TransfermarktRow = $tmRow
        TransfermarktPlayerId = $tmPlayerId
        TransfermarktPlayerName = $tmPlayerName
        DateKey = $dateKey
    }
}

$MainPath = Resolve-ScriptPath $MainPath
$SorareScoresPath = Resolve-ScriptPath $SorareScoresPath
$TransfermarktSquadsPath = Resolve-ScriptPath $TransfermarktSquadsPath
$ReviewWorkbookPath = Resolve-ScriptPath $ReviewWorkbookPath
$ManualCorrectionsPath = Resolve-ScriptPath $ManualCorrectionsPath
$CombinedOutputPath = Resolve-ScriptPath $CombinedOutputPath
$OutputMainPath = Resolve-ScriptPath $OutputMainPath
$BackupPath = Resolve-ScriptPath $BackupPath

foreach ($path in @($MainPath, $SorareScoresPath, $TransfermarktSquadsPath, $ReviewWorkbookPath)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required input not found: $path"
    }
}

if ($OutputMainPath -eq $MainPath -and -not (Test-Path -LiteralPath $BackupPath)) {
    Copy-Item -LiteralPath $MainPath -Destination $BackupPath
}

$reviewRows = Read-XlsxSheet $ReviewWorkbookPath 1
$reviewBySorareKey = @{}
$reviewByFallbackKey = @{}

function Add-ReviewMapping {
    param($Row)

    $tmPlayerId = Get-EffectiveReviewValue $row "manual_tm_player_id" "tm_player_id"
    $tmPlayerName = Get-EffectiveReviewValue $row "manual_tm_player_name" "tm_player_name"
    $tmClubId = Get-EffectiveReviewValue $row "manual_tm_club_id" "tm_club_id"

    if ([string]::IsNullOrWhiteSpace($tmPlayerId) -and [string]::IsNullOrWhiteSpace($tmPlayerName)) {
        return
    }

    $mapped = [pscustomobject]@{
        tm_player_id = $tmPlayerId
        tm_player_name = $tmPlayerName
        tm_club_id = $tmClubId
        match_status = $row.match_status
    }

    $reviewBySorareKey[(Get-SorarePlayerKey $row)] = $mapped
    $reviewByFallbackKey[(Get-FallbackPlayerKey $row)] = $mapped
}

foreach ($row in $reviewRows) {
    Add-ReviewMapping $row
}

if (Test-Path -LiteralPath $ManualCorrectionsPath) {
    foreach ($row in (Import-Csv -Path $ManualCorrectionsPath -Encoding UTF8)) {
        Add-ReviewMapping $row
    }
}

$tmRows = Import-Csv -Path $TransfermarktSquadsPath -Encoding UTF8
$tmSquadsByPlayerIdAndDate = @{}
$tmSquadsByNameClubAndDate = @{}
$duplicateTmIdDateKeys = 0
foreach ($row in $tmRows) {
    $dateKey = Get-DateKey $row.match_date
    $idKey = "$($row.tm_player_id)||$dateKey"
    if ($tmSquadsByPlayerIdAndDate.ContainsKey($idKey)) {
        $duplicateTmIdDateKeys += 1
    }
    else {
        $tmSquadsByPlayerIdAndDate[$idKey] = $row
    }

    $nameKey = "$(Normalize-Name $row.tm_player_name)||$(($row.sorare_club_slug).ToLowerInvariant())||$dateKey"
    if (-not $tmSquadsByNameClubAndDate.ContainsKey($nameKey)) {
        $tmSquadsByNameClubAndDate[$nameKey] = $row
    }
}

$combinedRows = New-Object System.Collections.Generic.List[object]
$combinedMatchedRows = 0
$sorareRows = Import-Csv -Path $SorareScoresPath -Encoding UTF8
foreach ($row in $sorareRows) {
    $context = Get-MatchContext $row
    $tmRow = $context.TransfermarktRow

    $out = [ordered]@{}
    foreach ($property in $row.PSObject.Properties) {
        $out[$property.Name] = $property.Value
    }

    if ($null -ne $tmRow) {
        $combinedMatchedRows += 1
        Set-Field $out "Lineup Status" (Get-CombinedStatus $tmRow.'Lineup Status')
        Set-Field $out "TM Minutes Played" $tmRow.'TM Minutes Played'
        Set-Field $out "TM Assists" $tmRow.'TM Assists'
        Set-Field $out "TM Goals" $tmRow.'TM Goals'
    }
    else {
        Set-Field $out "Lineup Status" "DNP"
        Set-Field $out "TM Minutes Played" ""
        Set-Field $out "TM Assists" ""
        Set-Field $out "TM Goals" ""
    }

    $combinedRows.Add([pscustomobject]$out)
}

$mainRows = Import-Csv -Path $MainPath -Encoding UTF8
$updatedMainRows = New-Object System.Collections.Generic.List[object]
$mainMatchedRows = 0
$mainReviewedRows = 0
foreach ($row in $mainRows) {
    $context = Get-MatchContext $row
    $tmRow = $context.TransfermarktRow
    $review = $context.Review

    $out = [ordered]@{}
    foreach ($property in $row.PSObject.Properties) {
        $out[$property.Name] = $property.Value
    }

    if ($null -ne $review) {
        $mainReviewedRows += 1
        Set-Field $out "transfermarkt_TransfermarktPlayerId" $context.TransfermarktPlayerId
        Set-Field $out "transfermarkt_TransfermarktPlayerName" $context.TransfermarktPlayerName
    }

    if ($null -ne $tmRow) {
        $mainMatchedRows += 1
        $mainStatus = Get-MainStatus $tmRow.'Lineup Status'
        Set-Field $out "transfermarkt_lineup_matched" $true
        Set-Field $out "transfermarkt_LineupStatus" $mainStatus
        Set-Field $out "transfermarkt_IsStarter" ($mainStatus -eq "starter")
        Set-Field $out "transfermarkt_IsBench" ($mainStatus -eq "bench")
        Set-Field $out "transfermarkt_IsDnp" $false
        Set-Field $out "transfermarkt_TMMinutesPlayed" $tmRow.'TM Minutes Played'
        Set-Field $out "transfermarkt_TMGoals" $tmRow.'TM Goals'
        Set-Field $out "transfermarkt_TMAssists" $tmRow.'TM Assists'
    }
    else {
        Set-Field $out "transfermarkt_lineup_matched" $false
        Set-Field $out "transfermarkt_LineupStatus" "dnp"
        Set-Field $out "transfermarkt_IsStarter" $false
        Set-Field $out "transfermarkt_IsBench" $false
        Set-Field $out "transfermarkt_IsDnp" $true
        Set-Field $out "transfermarkt_TMMinutesPlayed" ""
        Set-Field $out "transfermarkt_TMGoals" ""
        Set-Field $out "transfermarkt_TMAssists" ""
    }

    Set-Field $out "transfermarkt_review_context_source" $ReviewWorkbookPath
    $updatedMainRows.Add([pscustomobject]$out)
}

$combinedRows | Export-Csv -Path $CombinedOutputPath -NoTypeInformation -Encoding UTF8
$updatedMainRows | Export-Csv -Path $OutputMainPath -NoTypeInformation -Encoding UTF8

Write-Host "Review mappings loaded: $($reviewBySorareKey.Count)"
Write-Host "Transfermarkt squad rows loaded: $($tmRows.Count)"
Write-Host "Duplicate Transfermarkt player/date keys skipped: $duplicateTmIdDateKeys"
Write-Host "Wrote combined Sorare/Transfermarkt rows: $($combinedRows.Count) to $CombinedOutputPath"
Write-Host "Combined rows matched to Transfermarkt squad rows: $combinedMatchedRows"
Write-Host "Wrote updated main rows: $($updatedMainRows.Count) to $OutputMainPath"
Write-Host "Main rows with reviewed player mapping: $mainReviewedRows"
Write-Host "Main rows matched to Transfermarkt squad rows: $mainMatchedRows"
if (Test-Path -LiteralPath $BackupPath) {
    Write-Host "Backup available at $BackupPath"
}
