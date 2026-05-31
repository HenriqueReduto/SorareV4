import fs from "node:fs/promises";
import path from "node:path";

const root = path.resolve(decodeURIComponent(new URL("../../", import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, "$1"));
const mainPath = path.join(root, "data", "main", "main.csv");
const squadsPath = path.join(root, "data", "transfermarkt", "club_matchday_squads.csv");
const backupPath = path.join(root, "data", "transfermarkt", "club_matchday_squads_before_celtic_rangers_update.csv");

const targetClubSlugs = new Set(["celtic-glasgow", "rangers-glasgow"]);
const targetTeamByTitle = new Map([
  ["Celtic FC", "celtic-glasgow"],
  ["Rangers FC", "rangers-glasgow"],
]);

const requestHeaders = {
  "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
  "accept-language": "en-US,en;q=0.9",
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (inQuotes) {
      if (char === '"' && next === '"') {
        value += '"';
        i += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        value += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(value);
      value = "";
    } else if (char === "\n") {
      row.push(value);
      rows.push(row);
      row = [];
      value = "";
    } else if (char !== "\r") {
      value += char;
    }
  }

  if (value.length || row.length) {
    row.push(value);
    rows.push(row);
  }

  const [headers, ...data] = rows;
  return data
    .filter((cells) => cells.some((cell) => cell !== ""))
    .map((cells) => Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""])));
}

function toCsv(rows, headers) {
  const escapeCell = (value) => {
    const text = value == null ? "" : String(value);
    if (/[",\r\n]/.test(text)) {
      return `"${text.replaceAll('"', '""')}"`;
    }
    return text;
  };

  return [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => escapeCell(row[header])).join(",")),
  ].join("\n") + "\n";
}

function decodeHtml(value) {
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([a-f0-9]+);/gi, (_, code) => String.fromCodePoint(Number.parseInt(code, 16)))
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&uuml;/g, "ü")
    .replace(/&Uuml;/g, "Ü")
    .replace(/&ouml;/g, "ö")
    .replace(/&Ouml;/g, "Ö")
    .replace(/&auml;/g, "ä")
    .replace(/&Auml;/g, "Ä");
}

function stripTags(value) {
  return decodeHtml(value.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
}

function normalizeName(value) {
  return decodeHtml(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function dateOnly(value) {
  return value.slice(0, 10);
}

function gameIdFromUrl(value) {
  return value.match(/spielbericht\/(\d+)/)?.[1] ?? "";
}

function minuteFromStyle(style) {
  const match = style.match(/background-position:\s*-?(\d+)px\s+-?(\d+)px/);
  if (!match) return null;
  const x = Number(match[1]);
  const y = Number(match[2]);
  return Math.round(y / 36) * 10 + Math.round(x / 36) + 1;
}

async function fetchText(url) {
  const response = await fetch(url, { headers: requestHeaders });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} for ${url}`);
  }
  return response.text();
}

function collectRequiredFixtures(mainRows, existingRows) {
  const existingClubDates = new Set(existingRows.map((row) => `${row.sorare_club_slug}|${dateOnly(row.match_date)}`));
  const fixtureByGameId = new Map();

  for (const row of mainRows) {
    const clubSlug = row["Club Slug"];
    if (!targetClubSlugs.has(clubSlug)) continue;

    const fixtureDate = dateOnly(row["Game Date"]);
    if (existingClubDates.has(`${clubSlug}|${fixtureDate}`)) continue;

    const sourceUrl = row.transfermarkt_TransfermarktSourceUrl;
    const gameId = gameIdFromUrl(sourceUrl);
    if (!gameId) continue;

    if (!fixtureByGameId.has(gameId)) {
      fixtureByGameId.set(gameId, {
        game_id: gameId,
        url: sourceUrl,
        match_date_by_club: new Map(),
      });
    }

    fixtureByGameId.get(gameId).match_date_by_club.set(clubSlug, row["Game Date"]);
  }

  return [...fixtureByGameId.values()].sort((a, b) => Number(a.game_id) - Number(b.game_id));
}

function parseLineups(html) {
  const headingRegex = /<h2[^>]*>\s*<a title="([^"]+)" href="\/([^/]+)\/startseite\/verein\/(\d+)\/saison_id\/[^"]+">[\s\S]*?<\/a>\s*(Starting Line-up|Substitutes)\s*<\/h2>/g;
  const headings = [];
  let headingMatch;
  while ((headingMatch = headingRegex.exec(html))) {
    headings.push({
      index: headingMatch.index,
      teamName: decodeHtml(headingMatch[1]),
      tmSlug: headingMatch[2],
      tmClubId: headingMatch[3],
      section: headingMatch[4],
    });
  }

  const playerById = new Map();
  for (let i = 0; i < headings.length; i += 1) {
    const heading = headings[i];
    const sorareClubSlug = targetTeamByTitle.get(heading.teamName);
    if (!sorareClubSlug) continue;

    const sectionHtml = html.slice(heading.index, headings[i + 1]?.index ?? html.length);
    const playerRegex = /<a title="([^"]+)" class="wichtig" href="\/[^"]+\/leistungsdatendetails\/spieler\/(\d+)\/[^"]+">/g;
    let playerMatch;
    while ((playerMatch = playerRegex.exec(sectionHtml))) {
      const id = playerMatch[2];
      if (playerById.has(id)) continue;

      const name = decodeHtml(playerMatch[1]);
      playerById.set(id, {
        tm_player_id: id,
        tm_player_name: name,
        "Lineup Status Raw": heading.section === "Starting Line-up" ? "starting_lineup" : "substitutes",
        "Lineup Status": heading.section === "Starting Line-up" ? "Starter" : "Bench",
        tm_club_id: heading.tmClubId,
        sorare_club_slug: sorareClubSlug,
        transfermarkt_club_name: heading.teamName,
      });
    }
  }

  return playerById;
}

function sectionById(html, id) {
  const start = html.indexOf(`id="${id}"`);
  if (start < 0) return "";
  const next = html.indexOf('<div class="row">', start + 1);
  return html.slice(start, next < 0 ? html.length : next);
}

function parseListItems(html) {
  const items = [];
  const itemRegex = /<li class="sb-aktion-(heim|gast)">([\s\S]*?)<\/li>/g;
  let itemMatch;
  while ((itemMatch = itemRegex.exec(html))) {
    items.push({ side: itemMatch[1], html: itemMatch[2] });
  }
  return items;
}

function parseMatchEvents(html, players) {
  const stats = new Map([...players.keys()].map((id) => [id, { goals: 0, assists: 0, minutes: "" }]));

  for (const item of parseListItems(sectionById(html, "sb-tore"))) {
    const scorerId = item.html.match(/\/profil\/spieler\/(\d+)/)?.[1];
    const isOwnGoal = /Own-goal/i.test(stripTags(item.html));
    if (!isOwnGoal && stats.has(scorerId)) {
      stats.get(scorerId).goals += 1;
    }

    const assistId = item.html.match(/Assist:\s*<a[^>]+spieler\/(\d+)/)?.[1];
    if (stats.has(assistId)) {
      stats.get(assistId).assists += 1;
    }
  }

  const subOutMinuteByPlayer = new Map();
  const subInMinuteByPlayer = new Map();
  for (const item of parseListItems(sectionById(html, "sb-wechsel"))) {
    const minute = minuteFromStyle(item.html);
    const inId = item.html.match(/sb-aktion-wechsel-ein[\s\S]*?spieler\/(\d+)/)?.[1];
    const outId = item.html.match(/sb-aktion-wechsel-aus[\s\S]*?spieler\/(\d+)/)?.[1];
    if (minute == null) continue;

    if (inId) subInMinuteByPlayer.set(inId, minute);
    if (outId) subOutMinuteByPlayer.set(outId, minute);
  }

  for (const [id, player] of players) {
    const playerStats = stats.get(id);
    if (!playerStats) continue;

    if (player["Lineup Status"] === "Starter") {
      playerStats.minutes = String(Math.min(90, subOutMinuteByPlayer.get(id) ?? 90)) + ".0";
    } else if (subInMinuteByPlayer.has(id)) {
      playerStats.minutes = String(Math.max(0, 90 - subInMinuteByPlayer.get(id))) + ".0";
    }
  }

  return stats;
}

async function scrapeFixture(fixture) {
  const lineupHtml = await fetchText(fixture.url);
  const matchHtml = await fetchText(`https://www.transfermarkt.com/spielbericht/index/spielbericht/${fixture.game_id}`);
  const players = parseLineups(lineupHtml);
  const stats = parseMatchEvents(matchHtml, players);

  const rows = [];
  for (const [playerId, player] of players) {
    if (!fixture.match_date_by_club.has(player.sorare_club_slug)) continue;
    const playerStats = stats.get(playerId) ?? { goals: 0, assists: 0, minutes: "" };
    rows.push({
      game_id: fixture.game_id,
      tm_club_id: player.tm_club_id,
      tm_player_id: player.tm_player_id,
      tm_player_name: player.tm_player_name,
      "Lineup Status Raw": player["Lineup Status Raw"],
      "Lineup Status": player["Lineup Status"],
      match_date: fixture.match_date_by_club.get(player.sorare_club_slug),
      "TM Goals": player["Lineup Status"] === "Starter" || playerStats.minutes ? `${playerStats.goals}.0` : "",
      "TM Assists": player["Lineup Status"] === "Starter" || playerStats.minutes ? `${playerStats.assists}.0` : "",
      "TM Minutes Played": playerStats.minutes,
      sorare_club_slug: player.sorare_club_slug,
      transfermarkt_club_name: player.transfermarkt_club_name,
      tm_player_norm: normalizeName(player.tm_player_name),
    });
  }

  return rows;
}

const squadText = await fs.readFile(squadsPath, "utf8");
const existingRows = parseCsv(squadText);
const headers = squadText.slice(0, squadText.indexOf("\n")).replace(/\r$/, "").split(",");
const mainRows = parseCsv(await fs.readFile(mainPath, "utf8"));
const fixtures = collectRequiredFixtures(mainRows, existingRows);
const existingKeys = new Set(existingRows.map((row) => `${row.game_id}|${row.tm_club_id}|${row.tm_player_id}`));

console.log(`Missing Celtic/Rangers Transfermarkt fixtures to inspect: ${fixtures.length}`);

const appendedRows = [];
for (const fixture of fixtures) {
  console.log(`Fetching game ${fixture.game_id}: ${fixture.url}`);
  const rows = await scrapeFixture(fixture);
  const newRows = rows.filter((row) => !existingKeys.has(`${row.game_id}|${row.tm_club_id}|${row.tm_player_id}`));
  for (const row of newRows) {
    existingKeys.add(`${row.game_id}|${row.tm_club_id}|${row.tm_player_id}`);
  }
  appendedRows.push(...newRows);
  await new Promise((resolve) => setTimeout(resolve, 250));
}

try {
  await fs.access(backupPath);
} catch {
  await fs.copyFile(squadsPath, backupPath);
}

const updatedRows = [...existingRows, ...appendedRows].sort((a, b) => {
  const dateCompare = a.match_date.localeCompare(b.match_date);
  if (dateCompare) return dateCompare;
  const clubCompare = a.sorare_club_slug.localeCompare(b.sorare_club_slug);
  if (clubCompare) return clubCompare;
  return a.tm_player_name.localeCompare(b.tm_player_name);
});

await fs.writeFile(squadsPath, toCsv(updatedRows, headers), "utf8");

const appendedByClub = appendedRows.reduce((acc, row) => {
  acc[row.sorare_club_slug] = (acc[row.sorare_club_slug] ?? 0) + 1;
  return acc;
}, {});

console.log(`Appended rows: ${appendedRows.length}`);
console.log(JSON.stringify(appendedByClub, null, 2));
console.log(`Backup: ${backupPath}`);
