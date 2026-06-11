from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Song:
    song_id: str
    title: str
    aliases: tuple[str, ...]
    bpm: float | None = None
    artist: str = ""
    level: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_path(raw_path: str | Path, base_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(ch for ch in normalized if ch.isalnum())


def parse_optional_float(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_songs(path: Path) -> list[Song]:
    songs: list[Song] = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader, start=1):
            title = (row.get("title") or "").strip()
            if not title:
                raise ValueError(f"{path} line {index + 1}: missing title")
            aliases = tuple(
                alias.strip()
                for alias in (row.get("aliases") or "").replace(";", "|").split("|")
                if alias.strip()
            )
            songs.append(
                Song(
                    song_id=(row.get("id") or title).strip(),
                    title=title,
                    aliases=aliases,
                    bpm=parse_optional_float(row.get("bpm") or ""),
                    artist=(row.get("artist") or "").strip(),
                    level=(row.get("level") or "").strip(),
                )
            )
    return songs


class SongMatcher:
    def __init__(self, songs: list[Song], min_score: int) -> None:
        self.min_score = min_score
        self.entries: list[tuple[str, Song, str]] = []
        for song in songs:
            names = (song.title, *song.aliases)
            for name in names:
                normalized = normalize_text(name)
                if normalized:
                    self.entries.append((normalized, song, name))
        try:
            from rapidfuzz import fuzz
        except ImportError:
            self._fuzz = None
        else:
            self._fuzz = fuzz

    def match(self, text: str) -> tuple[Song, int, str] | None:
        normalized = normalize_text(text)
        if not normalized:
            return None

        best_song: Song | None = None
        best_score = 0
        best_name = ""
        for candidate, song, display_name in self.entries:
            if self._fuzz is None:
                score = 100 if candidate in normalized or normalized in candidate else 0
            else:
                score = int(self._fuzz.WRatio(normalized, candidate))
            if score > best_score:
                best_song = song
                best_score = score
                best_name = display_name

        if best_song is None or best_score < self.min_score:
            return None
        return best_song, best_score, best_name


class EventLog:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = path.open("a", encoding="utf-8", newline="\n")

    def write(self, event: str, **payload: Any) -> dict[str, Any]:
        row = {
            "event": event,
            "wall_time": now_iso(),
            "perf_s": time.perf_counter(),
            **payload,
        }
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._file.flush()
        return row

    def close(self) -> None:
        self._file.close()


class KeyboardDriver:
    def __init__(self, config: dict[str, Any], dry_run: bool) -> None:
        self.dry_run = dry_run
        self.press_s = float(config.get("press_ms", 35)) / 1000.0
        self.combo_hold_s = float(config.get("combo_hold_ms", 80)) / 1000.0
        if dry_run:
            self.controller = None
        else:
            from pynput.keyboard import Controller

            self.controller = Controller()

    def press(self, key: str) -> None:
        if self.dry_run:
            print(f"[dry-run] press {key}")
            return
        assert self.controller is not None
        self.controller.press(key)
        time.sleep(self.press_s)
        self.controller.release(key)

    def combo(self, keys: list[str]) -> None:
        if self.dry_run:
            print(f"[dry-run] combo {'+'.join(keys)}")
            return
        assert self.controller is not None
        for key in keys:
            self.controller.press(key)
        time.sleep(self.combo_hold_s)
        for key in reversed(keys):
            self.controller.release(key)


class MarkerTone:
    def __init__(self, config: dict[str, Any], dry_run: bool) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.frequency_hz = int(config.get("frequency_hz", 15000))
        self.duration_ms = int(config.get("duration_ms", 60))
        self.dry_run = dry_run
        self._winsound = None
        if self.enabled and not dry_run:
            try:
                import winsound
            except ImportError:
                print("Marker tone is enabled, but winsound is unavailable on this OS.")
                self.enabled = False
            else:
                self._winsound = winsound

    def emit_async(self) -> None:
        if not self.enabled:
            return
        if self.dry_run:
            print(
                f"[dry-run] marker {self.frequency_hz}Hz for {self.duration_ms}ms"
            )
            return

        def play() -> None:
            assert self._winsound is not None
            self._winsound.Beep(self.frequency_hz, self.duration_ms)

        threading.Thread(target=play, daemon=True).start()


class ObsRecorder:
    def __init__(self, config: dict[str, Any], dry_run: bool) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.stop_at_end = bool(config.get("stop_recording_at_end", True))
        self.dry_run = dry_run
        self.client = None
        self.config = config

    def connect(self) -> None:
        if not self.enabled or self.dry_run:
            return
        import obsws_python as obs

        self.client = obs.ReqClient(
            host=self.config.get("host", "localhost"),
            port=int(self.config.get("port", 4455)),
            password=self.config.get("password", ""),
            timeout=5,
        )

    def start(self) -> None:
        if not self.enabled:
            return
        if self.dry_run:
            print("[dry-run] OBS start recording")
            return
        if self.client is None:
            self.connect()
        status = self.client.get_record_status()
        if not status.output_active:
            self.client.start_record()

    def stop(self) -> None:
        if not self.enabled or not self.stop_at_end:
            return
        if self.dry_run:
            print("[dry-run] OBS stop recording")
            return
        if self.client is None:
            return
        status = self.client.get_record_status()
        if status.output_active:
            self.client.stop_record()


class OcrReader:
    def __init__(self, config: dict[str, Any], dry_run: bool) -> None:
        self.enabled = bool(config.get("enabled", True))
        self.dry_run = dry_run
        self.config = config
        self.region = dict(config.get("title_region", {}))
        self.poll_interval_s = float(config.get("poll_interval_s", 0.45))
        if not self.enabled:
            self.reader = None
            self.sct = None
            return
        engine = config.get("engine", "easyocr")
        if engine != "easyocr":
            raise ValueError("Only easyocr is currently implemented.")
        import easyocr
        import mss

        self.sct = mss.mss()
        self.reader = easyocr.Reader(
            config.get("languages", ["ja", "en"]),
            gpu=bool(config.get("gpu", False)),
        )

    def read_text(self) -> str:
        if not self.enabled:
            return ""
        if not self.region:
            raise ValueError("ocr.title_region must be configured")
        import numpy as np

        assert self.sct is not None
        assert self.reader is not None
        shot = self.sct.grab(self.region)
        image = np.asarray(shot)
        rgb = image[:, :, :3][:, :, ::-1]
        results = self.reader.readtext(rgb, detail=1, paragraph=False)
        texts: list[str] = []
        for _box, text, confidence in results:
            if confidence >= 0.15:
                texts.append(str(text))
        return " ".join(texts).strip()


class MaiDelayMeasurer:
    def __init__(
        self,
        config_path: Path,
        dry_run: bool,
        max_tracks: int | None = None,
        max_selection_moves: int | None = None,
    ) -> None:
        self.config_path = config_path.resolve()
        self.config_dir = self.config_path.parent
        self.config = load_json(self.config_path)
        self.dry_run = dry_run
        if max_tracks is not None:
            self.config["max_tracks"] = max_tracks
        if max_selection_moves is not None:
            self.config["max_selection_moves"] = max_selection_moves

        songs_csv = resolve_path(self.config["songs_csv"], self.config_dir)
        self.songs = load_songs(songs_csv)
        self.matcher = SongMatcher(
            self.songs,
            min_score=int(self.config.get("ocr", {}).get("min_match_score", 82)),
        )

        self.keyboard = KeyboardDriver(self.config.get("keyboard", {}), dry_run)
        self.marker = MarkerTone(self.config.get("marker", {}), dry_run)
        self.ocr = OcrReader(self.config.get("ocr", {}), dry_run)
        self.obs = ObsRecorder(self.config.get("obs", {}), dry_run)

        output_dir = resolve_path(self.config.get("output_dir", "measurement/runs"), self.config_dir)
        run_name = datetime.now().strftime("mai_%Y%m%d_%H%M%S")
        self.run_dir = output_dir / run_name
        self.log = EventLog(self.run_dir / "events.jsonl")
        self.summary_csv = self.run_dir / "summary.csv"

    def wait(self, seconds: float) -> None:
        if self.dry_run:
            time.sleep(min(seconds, 0.2))
        else:
            time.sleep(seconds)

    def locate_song(self) -> tuple[Song | None, str, int, str]:
        if not self.ocr.enabled:
            return None, "", 0, ""

        stable_reads = int(self.config.get("ocr", {}).get("stable_reads", 2))
        unknown_retry_limit = int(
            self.config.get("ocr", {}).get("unknown_retry_limit", 3)
        )
        seen: Counter[str] = Counter()
        last_raw = ""
        last_score = 0
        last_name = ""

        for _ in range(max(stable_reads, unknown_retry_limit)):
            raw = self.ocr.read_text()
            last_raw = raw
            matched = self.matcher.match(raw)
            if matched is not None:
                song, score, matched_name = matched
                seen[song.song_id] += 1
                last_score = score
                last_name = matched_name
                if seen[song.song_id] >= stable_reads:
                    return song, raw, score, matched_name
            self.wait(self.ocr.poll_interval_s)

        return None, last_raw, last_score, last_name

    def write_summary_header(self) -> None:
        self.summary_csv.parent.mkdir(parents=True, exist_ok=True)
        with self.summary_csv.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    "track_index",
                    "song_id",
                    "title",
                    "bpm",
                    "start_perf_s",
                    "skip_perf_s",
                    "ocr_text",
                    "ocr_score",
                ]
            )

    def append_summary(
        self,
        track_index: int,
        song: Song,
        start_event: dict[str, Any],
        skip_event: dict[str, Any],
        ocr_text: str,
        ocr_score: int,
    ) -> None:
        with self.summary_csv.open("a", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(
                [
                    track_index,
                    song.song_id,
                    song.title,
                    song.bpm if song.bpm is not None else "",
                    start_event["perf_s"],
                    skip_event["perf_s"],
                    ocr_text,
                    ocr_score,
                ]
            )

    def measure_current_song(
        self,
        track_index: int,
        song: Song,
        ocr_text: str,
        ocr_score: int,
        matched_name: str,
    ) -> None:
        keyboard_config = self.config.get("keyboard", {})
        timing = self.config.get("timing", {})
        start_key = keyboard_config.get("start_key", "c")
        skip_keys = list(keyboard_config.get("skip_keys", ["e", "d", "q", "a"]))

        self.wait(float(timing.get("selection_settle_s", 0.8)))
        self.marker.emit_async()
        start_event = self.log.write(
            "start_pressed",
            track_index=track_index,
            song_id=song.song_id,
            title=song.title,
            bpm=song.bpm,
            ocr_text=ocr_text,
            ocr_score=ocr_score,
            matched_name=matched_name,
            marker_enabled=self.marker.enabled,
        )
        self.keyboard.press(start_key)

        self.wait(float(timing.get("song_play_window_s", 30.0)))
        skip_event = self.log.write(
            "skip_pressed",
            track_index=track_index,
            song_id=song.song_id,
            title=song.title,
        )
        self.keyboard.combo(skip_keys)
        self.append_summary(
            track_index, song, start_event, skip_event, ocr_text, ocr_score
        )
        self.wait(float(timing.get("after_skip_wait_s", 8.0)))

    def run(self) -> None:
        max_tracks = int(self.config.get("max_tracks", 99))
        max_selection_moves = int(self.config.get("max_selection_moves", 600))
        if self.dry_run:
            max_tracks = min(max_tracks, 3)
            max_selection_moves = min(max_selection_moves, 10)
        keyboard_config = self.config.get("keyboard", {})
        timing = self.config.get("timing", {})
        next_key = keyboard_config.get("next_key", "d")

        self.write_summary_header()
        self.log.write(
            "run_started",
            dry_run=self.dry_run,
            config=str(self.config_path),
            run_dir=str(self.run_dir),
            songs=len(self.songs),
        )

        measured_tracks = 0
        selection_moves = 0
        try:
            self.obs.connect()
            self.obs.start()
            record_event = self.log.write("recording_started")
            print(f"Run directory: {self.run_dir}")
            print(f"Recording reference perf_s: {record_event['perf_s']:.6f}")
            self.wait(float(timing.get("recording_start_warmup_s", 3.0)))

            while measured_tracks < max_tracks and selection_moves < max_selection_moves:
                if self.ocr.enabled:
                    song, raw_text, score, matched_name = self.locate_song()
                else:
                    song = Song(
                        song_id=f"track_{measured_tracks + 1:03d}",
                        title=f"Track {measured_tracks + 1:03d}",
                        aliases=(),
                    )
                    raw_text = ""
                    score = 0
                    matched_name = ""

                if song is None:
                    self.log.write(
                        "selection_skipped",
                        reason="ocr_no_shared_song_match",
                        ocr_text=raw_text,
                        ocr_score=score,
                    )
                    self.keyboard.press(next_key)
                    selection_moves += 1
                    self.wait(float(timing.get("after_next_wait_s", 1.0)))
                    continue

                measured_tracks += 1
                print(
                    f"[{measured_tracks}/{max_tracks}] {song.title}"
                    f" (OCR score {score})"
                )
                self.measure_current_song(
                    measured_tracks, song, raw_text, score, matched_name
                )
                self.keyboard.press(next_key)
                selection_moves += 1
                self.wait(float(timing.get("after_next_wait_s", 1.0)))

            self.log.write(
                "run_finished",
                measured_tracks=measured_tracks,
                selection_moves=selection_moves,
            )
        except KeyboardInterrupt:
            self.log.write(
                "run_interrupted",
                measured_tracks=measured_tracks,
                selection_moves=selection_moves,
            )
            raise
        finally:
            self.obs.stop()
            self.log.write("recording_stopped")
            self.log.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure maimai start delay by OCR-selecting shared songs."
    )
    parser.add_argument(
        "--config",
        default="measurement/config.example.json",
        help="Path to measurement config JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialize logs and print actions without pressing keys or using OBS.",
    )
    parser.add_argument("--max-tracks", type=int, help="Override max_tracks.")
    parser.add_argument(
        "--max-selection-moves",
        type=int,
        help="Override max_selection_moves.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    measurer = MaiDelayMeasurer(
        Path(args.config),
        dry_run=args.dry_run,
        max_tracks=args.max_tracks,
        max_selection_moves=args.max_selection_moves,
    )
    measurer.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
