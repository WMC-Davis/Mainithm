from __future__ import annotations

import csv
import json
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any


DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json"
ALIAS_URL = "https://www.yuzuchan.moe/api/v2/aliases/maimaidx/aliases"
LXNS_SONG_URL = "https://maimai.lxns.net/api/v0/maimai/song/list?notes=true"
LXNS_ALIAS_URL = "https://maimai.lxns.net/api/v0/maimai/alias/list"
OUTPUT_PATH = Path(__file__).with_name("maimai_master_songs.csv")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_data() -> dict[str, Any]:
    return fetch_json(DATA_URL)


def normalize_title(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def add_alias_values(
    aliases: dict[str, list[str]], title: object, values: list[object]
) -> None:
    normalized_title = normalize_title(title)
    if not normalized_title:
        return
    alias_list = aliases.setdefault(normalized_title, [])
    seen = {alias.casefold() for alias in alias_list}
    for value in values:
        text = " ".join(str(value).split())
        key = text.casefold()
        if text and key not in seen:
            alias_list.append(text)
            seen.add(key)


def fetch_aliases() -> dict[str, str]:
    aliases: dict[str, list[str]] = {}

    for item in fetch_json(ALIAS_URL):
        add_alias_values(aliases, item.get("name"), item.get("alias", []))

    lxns_songs = fetch_json(LXNS_SONG_URL).get("songs", [])
    lxns_title_by_id = {int(song["id"]): song["title"] for song in lxns_songs}
    for item in fetch_json(LXNS_ALIAS_URL).get("aliases", []):
        song_id = item.get("song_id")
        if song_id is None:
            continue
        title = lxns_title_by_id.get(int(song_id))
        if title is not None:
            add_alias_values(aliases, title, item.get("aliases", []))

    return {title: "|".join(values) for title, values in aliases.items()}


def level_sort_value(level: object) -> float:
    text = str(level or "").strip()
    if text.endswith("+"):
        return float(text[:-1]) + 0.5
    try:
        return float(text)
    except ValueError:
        return 0.0


def sheet_id(song_index: int, sheet_type: object) -> int:
    return song_index


def song_type_label(sheets: list[dict[str, Any]]) -> str:
    types = {str(sheet.get("type", "")).lower() for sheet in sheets}
    labels = []
    if "dx" in types:
        labels.append("DX")
    if "std" in types:
        labels.append("STD")
    return "/".join(labels)


def main() -> None:
    data = fetch_data()
    aliases = fetch_aliases()
    version_abbr = {
        item["version"]: item.get("abbr") or item["version"]
        for item in data.get("versions", [])
    }
    type_name = {
        item["type"]: item.get("abbr") or item.get("name") or item["type"]
        for item in data.get("types", [])
    }
    difficulty_name = {
        item["difficulty"]: item.get("name") or item["difficulty"].upper()
        for item in data.get("difficulties", [])
    }

    rows: list[dict[str, Any]] = []
    for song_index, song in enumerate(data.get("songs", []), start=1):
        for sheet in song.get("sheets", []):
            if sheet.get("difficulty") != "master":
                continue
            sheet_type = sheet.get("type")
            sheet_version = sheet.get("version") or song.get("version") or ""
            rows.append(
                {
                    "No.": sheet_id(song_index, sheet_type),
                    "乐曲类型": song_type_label(song.get("sheets", [])),
                    "曲名": song.get("title", ""),
                    "类型": type_name.get(sheet_type, sheet_type or ""),
                    "难易度": difficulty_name.get(
                        sheet.get("difficulty"), str(sheet.get("difficulty", "")).upper()
                    ),
                    "等级": sheet.get("level", ""),
                    "谱面定数": (
                        sheet.get("internalLevelValue")
                        if sheet.get("internalLevelValue") is not None
                        else sheet.get("internalLevel")
                        if sheet.get("internalLevel") is not None
                        else sheet.get("levelValue", "")
                    ),
                    "BPM": song.get("bpm", ""),
                    "版本": version_abbr.get(sheet_version, sheet_version),
                    "追加日期": song.get("releaseDate", ""),
                    "是否锁定": "是" if song.get("isLocked") else "否",
                    "别名": aliases.get(normalize_title(song.get("title", "")), ""),
                }
            )

    rows.sort(key=lambda row: (level_sort_value(row["等级"]), int(row["No."])), reverse=True)

    fieldnames = [
        "No.",
        "乐曲类型",
        "曲名",
        "类型",
        "难易度",
        "等级",
        "谱面定数",
        "BPM",
        "版本",
        "追加日期",
        "是否锁定",
        "别名",
    ]
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"Source updateTime: {data.get('updateTime', '')}")


if __name__ == "__main__":
    main()
