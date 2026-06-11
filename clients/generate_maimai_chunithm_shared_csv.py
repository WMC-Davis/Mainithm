from __future__ import annotations

import csv
import json
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from clients.generate_chunithm_songs_csv import fetch_aliases as fetch_chunithm_aliases
from clients.generate_maimai_master_csv import fetch_aliases as fetch_maimai_aliases


MAIMAI_DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/maimai/data.json"
CHUNITHM_DATA_URL = "https://dp4p6x0xfi5o9.cloudfront.net/chunithm/data.json"
OUTPUT_PATH = Path(__file__).with_name("maimai_chunithm_shared_songs.csv")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def normalize_title(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).casefold()


def type_abbr_map(data: dict[str, Any]) -> dict[str, str]:
    return {
        item["type"]: item.get("abbr") or item.get("name") or item["type"]
        for item in data.get("types", [])
    }


def maimai_sheet_id(song_index: int, sheet_type: object) -> int:
    return song_index


def maimai_song_type_label(sheets: list[dict[str, Any]]) -> str:
    types = {str(sheet.get("type", "")).lower() for sheet in sheets}
    labels = []
    if "dx" in types:
        labels.append("DX")
    if "std" in types:
        labels.append("STD")
    return "/".join(labels)


def grouped_sheet_labels(
    sheets: list[dict[str, Any]],
    type_abbr: dict[str, str],
    *,
    exclude_types: set[str] | None = None,
) -> tuple[str, str]:
    exclude_types = exclude_types or set()
    ids_by_type: dict[str, str] = {}
    levels_by_type: dict[str, list[str]] = {}

    for sheet in sheets:
        sheet_type = str(sheet.get("type", ""))
        if sheet_type in exclude_types:
            continue
        label = type_abbr.get(sheet_type, sheet_type.upper())
        levels_by_type.setdefault(label, []).append(str(sheet.get("level", "")))

    for label, levels in levels_by_type.items():
        levels_by_type[label] = [level for level in levels if level]

    levels_text = " ; ".join(
        " | ".join(f"{label} {level}" for level in levels)
        for label, levels in levels_by_type.items()
        if levels
    )
    ids_text = ""
    return ids_text, levels_text


def maimai_info(
    song: dict[str, Any],
    song_index: int,
    type_abbr: dict[str, str],
    aliases: dict[str, str],
) -> dict[str, Any]:
    sheets = [sheet for sheet in song.get("sheets", []) if sheet.get("type") != "utage"]
    _unused_ids, sheet_text = grouped_sheet_labels(
        sheets,
        type_abbr,
        exclude_types={"utage"},
    )
    return {
        "舞萌ID": maimai_sheet_id(song_index, None),
        "舞萌类型": maimai_song_type_label(sheets),
        "舞萌分类": song.get("category", ""),
        "舞萌谱面": sheet_text,
        "舞萌BPM": song.get("bpm", "") if song.get("bpm") is not None else "",
        "舞萌版本": song.get("version", ""),
        "舞萌追加日期": song.get("releaseDate", ""),
        "舞萌是否锁定": "是" if song.get("isLocked") else "否",
        "舞萌别名": aliases.get(normalize_title(song.get("title", "")), ""),
    }


def chunithm_sheet_label(sheet: dict[str, Any], type_abbr: dict[str, str]) -> str:
    sheet_type = str(sheet.get("type", ""))
    label = type_abbr.get(sheet_type, sheet_type.upper())
    if sheet_type == "we":
        return f"{label} {sheet.get('difficulty', '')}{sheet.get('level', '')}"
    return f"{label} {sheet.get('level', '')}"


def chunithm_info(
    song: dict[str, Any],
    song_index: int,
    type_abbr: dict[str, str],
    aliases: dict[str, str],
) -> dict[str, Any]:
    sheets = [sheet for sheet in song.get("sheets", []) if sheet.get("type") != "we"]
    return {
        "中二No.": song_index,
        "中二分类": song.get("category", ""),
        "中二创作者": song.get("artist", ""),
        "中二谱面": " | ".join(chunithm_sheet_label(sheet, type_abbr) for sheet in sheets),
        "中二BPM": song.get("bpm", "") if song.get("bpm") is not None else "",
        "中二版本": song.get("version", ""),
        "中二别名": aliases.get(normalize_title(song.get("title", "")), ""),
    }


def main() -> None:
    maimai_data = fetch_json(MAIMAI_DATA_URL)
    chunithm_data = fetch_json(CHUNITHM_DATA_URL)
    maimai_aliases = fetch_maimai_aliases()
    chunithm_aliases = fetch_chunithm_aliases()
    maimai_types = type_abbr_map(maimai_data)
    chunithm_types = type_abbr_map(chunithm_data)

    maimai_by_title: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, song in enumerate(maimai_data.get("songs", []), start=1):
        if song.get("category") == "宴会場":
            continue
        sheets = [sheet for sheet in song.get("sheets", []) if sheet.get("type") != "utage"]
        if not sheets:
            continue
        maimai_by_title.setdefault(normalize_title(song.get("title")), (index, song))

    chunithm_by_title: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, song in enumerate(chunithm_data.get("songs", []), start=1):
        if song.get("category") == "WORLD'S END":
            continue
        sheets = [sheet for sheet in song.get("sheets", []) if sheet.get("type") != "we"]
        if not sheets:
            continue
        chunithm_by_title.setdefault(normalize_title(song.get("title")), (index, song))

    shared_titles = sorted(
        set(maimai_by_title) & set(chunithm_by_title),
        key=lambda title: maimai_by_title[title][0],
        reverse=True,
    )

    rows: list[dict[str, Any]] = []
    for title in shared_titles:
        maimai_index, maimai_song = maimai_by_title[title]
        chunithm_index, chunithm_song = chunithm_by_title[title]
        rows.append(
            {
                "曲名": maimai_song.get("title", ""),
                **maimai_info(maimai_song, maimai_index, maimai_types, maimai_aliases),
                **chunithm_info(
                    chunithm_song,
                    chunithm_index,
                    chunithm_types,
                    chunithm_aliases,
                ),
            }
        )

    fieldnames = [
        "曲名",
        "舞萌ID",
        "舞萌类型",
        "舞萌分类",
        "舞萌谱面",
        "舞萌BPM",
        "舞萌版本",
        "舞萌追加日期",
        "舞萌是否锁定",
        "舞萌别名",
        "中二No.",
        "中二分类",
        "中二创作者",
        "中二谱面",
        "中二BPM",
        "中二版本",
        "中二别名",
    ]
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"maimai updateTime: {maimai_data.get('updateTime', '')}")
    print(f"CHUNITHM updateTime: {chunithm_data.get('updateTime', '')}")


if __name__ == "__main__":
    main()
