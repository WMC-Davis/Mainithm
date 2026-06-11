from __future__ import annotations

import csv
import json
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any


DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/chunithm/data.json"
ALIAS_URL = "https://raw.githubusercontent.com/AmethystTim/chunithm-alias/master/alias.json"
OUTPUT_PATH = Path(__file__).with_name("chunithm_songs.csv")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_data() -> dict[str, Any]:
    return fetch_json(DATA_URL)


def normalize_title(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def fetch_aliases() -> dict[str, str]:
    aliases: dict[str, list[str]] = {}
    for item in fetch_json(ALIAS_URL).get("songs", []):
        title = normalize_title(item.get("songId"))
        if not title:
            continue
        alias_list = aliases.setdefault(title, [])
        seen = {alias.casefold() for alias in alias_list}
        for alias in item.get("aliases", []):
            text = " ".join(str(alias).split())
            key = text.casefold()
            if text and key not in seen:
                alias_list.append(text)
                seen.add(key)
    return {title: "|".join(values) for title, values in aliases.items()}


def sheet_label(sheet: dict[str, Any], type_abbr: dict[str, str]) -> str:
    sheet_type = sheet.get("type", "")
    prefix = type_abbr.get(sheet_type, str(sheet_type).upper())
    difficulty = sheet.get("difficulty", "")
    level = sheet.get("level", "")

    if sheet_type == "we":
        return f"{prefix} {difficulty}{level}"
    return f"{prefix} {level}"


def main() -> None:
    data = fetch_data()
    aliases = fetch_aliases()
    type_abbr = {
        item["type"]: item.get("abbr") or item.get("name") or item["type"]
        for item in data.get("types", [])
    }

    rows: list[dict[str, Any]] = []
    for song_index, song in enumerate(data.get("songs", []), start=1):
        rows.append(
            {
                "No.": song_index,
                "分类": song.get("category", ""),
                "曲名": song.get("title", ""),
                "创作者": song.get("artist", ""),
                "谱面": " | ".join(
                    sheet_label(sheet, type_abbr) for sheet in song.get("sheets", [])
                ),
                "BPM": song.get("bpm", "") if song.get("bpm") is not None else "",
                "版本": song.get("version", ""),
                "别名": aliases.get(normalize_title(song.get("title", "")), ""),
            }
        )

    rows.sort(key=lambda row: int(row["No."]), reverse=True)

    fieldnames = ["No.", "分类", "曲名", "创作者", "谱面", "BPM", "版本", "别名"]
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"Source updateTime: {data.get('updateTime', '')}")


if __name__ == "__main__":
    main()
