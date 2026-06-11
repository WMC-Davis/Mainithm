from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class Trial:
    track_index: int
    song_id: str
    title: str
    bpm: float | None
    start_perf_s: float
    skip_perf_s: float | None
    start_event: dict[str, Any]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_path(raw_path: str | Path, base_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                events.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} line {line_number}: invalid JSON") from exc
    return events


def parse_bpm(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_trials(events: list[dict[str, Any]]) -> list[Trial]:
    skips: dict[int, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "skip_pressed":
            skips[int(event["track_index"])] = event

    trials: list[Trial] = []
    for event in events:
        if event.get("event") != "start_pressed":
            continue
        track_index = int(event["track_index"])
        skip_event = skips.get(track_index)
        trials.append(
            Trial(
                track_index=track_index,
                song_id=str(event.get("song_id", "")),
                title=str(event.get("title", "")),
                bpm=parse_bpm(event.get("bpm")),
                start_perf_s=float(event["perf_s"]),
                skip_perf_s=float(skip_event["perf_s"]) if skip_event else None,
                start_event=event,
            )
        )
    return trials


def extract_audio(recording: Path, wav_path: Path, sample_rate: int) -> None:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(recording),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-sample_fmt",
        "s16",
        str(wav_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.readframes(wav.getnframes())

    if sample_width != 2:
        raise ValueError(f"Expected 16-bit WAV, got sample width {sample_width}")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sample_rate


def frame_rms(
    audio: np.ndarray,
    sample_rate: int,
    start_s: float,
    end_s: float,
    window_ms: float,
    hop_ms: float,
) -> tuple[np.ndarray, np.ndarray]:
    start_sample = max(0, int(start_s * sample_rate))
    end_sample = min(len(audio), int(end_s * sample_rate))
    segment = audio[start_sample:end_sample]
    window = max(1, int(sample_rate * window_ms / 1000.0))
    hop = max(1, int(sample_rate * hop_ms / 1000.0))
    if len(segment) < window:
        return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

    frames = np.lib.stride_tricks.sliding_window_view(segment, window)[::hop]
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    times = (np.arange(len(rms)) * hop + window / 2) / sample_rate + start_s
    return times, rms


def robust_threshold(values: np.ndarray, sigma: float) -> float:
    if len(values) == 0:
        return math.inf
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return median + sigma * 1.4826 * max(mad, 1e-9)


def pick_local_peaks(
    times: np.ndarray,
    values: np.ndarray,
    threshold: float,
    min_distance_s: float,
) -> list[tuple[float, float]]:
    peaks: list[tuple[float, float]] = []
    if len(values) < 3:
        return peaks
    for index in range(1, len(values) - 1):
        value = float(values[index])
        if value < threshold:
            continue
        if value < float(values[index - 1]) or value < float(values[index + 1]):
            continue
        peak_time = float(times[index])
        if peaks and peak_time - peaks[-1][0] < min_distance_s:
            if value > peaks[-1][1]:
                peaks[-1] = (peak_time, value)
        else:
            peaks.append((peak_time, value))
    return peaks


def find_countdown_end(
    audio: np.ndarray,
    sample_rate: int,
    trial: Trial,
    start_ref_s: float,
    config: dict[str, Any],
) -> tuple[float | None, str]:
    search_start = start_ref_s + float(config.get("countdown_search_start_s", 3.5))
    search_end = start_ref_s + float(config.get("countdown_search_end_s", 16.0))
    times, rms = frame_rms(audio, sample_rate, search_start, search_end, 20, 10)
    if len(rms) == 0:
        return None, "no_countdown_window"

    threshold = robust_threshold(rms, sigma=4.0)
    peaks = pick_local_peaks(times, rms, threshold, min_distance_s=0.12)
    if len(peaks) < 3:
        return None, "few_countdown_peaks"

    if trial.bpm and trial.bpm > 0:
        beat_s = 60.0 / trial.bpm
        tolerance = max(0.055, beat_s * 0.24)
        best_run: list[tuple[float, float]] = []
        current: list[tuple[float, float]] = [peaks[0]]
        for peak in peaks[1:]:
            gap = peak[0] - current[-1][0]
            if abs(gap - beat_s) <= tolerance:
                current.append(peak)
            else:
                if len(current) > len(best_run):
                    best_run = current
                current = [peak]
        if len(current) > len(best_run):
            best_run = current
        if len(best_run) >= 3:
            return best_run[-1][0], "bpm_countdown"

    best_run = []
    current = [peaks[0]]
    previous_gap: float | None = None
    for peak in peaks[1:]:
        gap = peak[0] - current[-1][0]
        is_beat_like = 0.2 <= gap <= 1.5
        is_regular = previous_gap is None or abs(gap - previous_gap) <= max(
            0.08, previous_gap * 0.28
        )
        if is_beat_like and is_regular:
            current.append(peak)
            previous_gap = gap if previous_gap is None else (previous_gap + gap) / 2
        else:
            if len(current) > len(best_run):
                best_run = current
            current = [peak]
            previous_gap = None
    if len(current) > len(best_run):
        best_run = current
    if len(best_run) >= 3:
        return best_run[-1][0], "regular_countdown"
    return None, "no_regular_countdown"


def detect_marker_times(
    audio: np.ndarray,
    sample_rate: int,
    marker_config: dict[str, Any],
    detect_config: dict[str, Any],
) -> list[float]:
    if not marker_config.get("enabled", False) or not detect_config.get("enabled", True):
        return []

    frequency_hz = float(marker_config.get("frequency_hz", 15000))
    window = int(detect_config.get("fft_window", 2048))
    hop = int(detect_config.get("fft_hop", 512))
    min_gap_s = float(detect_config.get("min_gap_s", 5.0))
    threshold_sigma = float(detect_config.get("threshold_sigma", 8.0))

    if len(audio) < window:
        return []

    chunk_samples = sample_rate * 30
    bin_index = int(round(frequency_hz * window / sample_rate))
    bin_index = max(1, min(bin_index, window // 2 - 2))
    scores: list[np.ndarray] = []
    score_times: list[np.ndarray] = []
    hann = np.hanning(window).astype(np.float32)

    for chunk_start in range(0, len(audio) - window + 1, chunk_samples):
        chunk_end = min(len(audio), chunk_start + chunk_samples + window)
        chunk = audio[chunk_start:chunk_end]
        if len(chunk) < window:
            continue
        frames = np.lib.stride_tricks.sliding_window_view(chunk, window)[::hop]
        spectrum = np.abs(np.fft.rfft(frames * hann, axis=1))
        tone = spectrum[:, bin_index - 1 : bin_index + 2].mean(axis=1)
        floor = np.median(spectrum[:, 2:], axis=1) + 1e-9
        score = tone / floor
        times = (np.arange(len(score)) * hop + window / 2 + chunk_start) / sample_rate
        scores.append(score)
        score_times.append(times)

    if not scores:
        return []

    all_scores = np.concatenate(scores)
    all_times = np.concatenate(score_times)
    threshold = robust_threshold(all_scores, sigma=threshold_sigma)
    hot = all_scores >= threshold

    marker_times: list[float] = []
    index = 0
    while index < len(hot):
        if not hot[index]:
            index += 1
            continue
        start = index
        while index < len(hot) and hot[index]:
            index += 1
        stop = index
        local = all_scores[start:stop]
        local_times = all_times[start:stop]
        peak_time = float(local_times[int(np.argmax(local))])
        if not marker_times or peak_time - marker_times[-1] >= min_gap_s:
            marker_times.append(peak_time)
        elif float(local.max()) > all_scores[np.argmin(np.abs(all_times - marker_times[-1]))]:
            marker_times[-1] = peak_time

    return marker_times


def pair_start_references(
    trials: list[Trial],
    marker_times: list[float],
    recording_start_perf_s: float | None,
    tolerance_s: float = 5.0,
) -> tuple[list[float], list[str]]:
    references: list[float] = []
    sources: list[str] = []
    used_markers: set[int] = set()

    for index, trial in enumerate(trials):
        expected = (
            trial.start_perf_s - recording_start_perf_s
            if recording_start_perf_s is not None
            else None
        )
        marker_index: int | None = None
        if marker_times:
            if expected is not None:
                candidates = [
                    (abs(marker - expected), i)
                    for i, marker in enumerate(marker_times)
                    if i not in used_markers
                ]
                if candidates:
                    distance, best_i = min(candidates)
                    if distance <= tolerance_s:
                        marker_index = best_i
            elif index < len(marker_times):
                marker_index = index

        if marker_index is not None:
            used_markers.add(marker_index)
            references.append(marker_times[marker_index])
            sources.append("marker")
            continue

        if expected is None:
            raise ValueError(
                "Cannot align trials: no marker detected and no recording_started event."
            )
        references.append(expected)
        sources.append("obs_time_fallback")

    return references, sources


def analyze_trial(
    audio: np.ndarray,
    sample_rate: int,
    trial: Trial,
    start_ref_s: float,
    ref_source: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    mode = str(config.get("mode", "peak"))
    skip_guard_s = float(config.get("skip_guard_s", 1.0))
    ignore_after_start_s = float(config.get("ignore_after_start_s", 7.0))
    post_countdown_silence_s = float(config.get("post_countdown_silence_s", 0.25))

    countdown_end_s, countdown_method = find_countdown_end(
        audio, sample_rate, trial, start_ref_s, config
    )
    if countdown_end_s is None:
        warnings.append(countdown_method)

    search_start_s = start_ref_s + ignore_after_start_s
    if countdown_end_s is not None:
        search_start_s = max(search_start_s, countdown_end_s + post_countdown_silence_s)

    if trial.skip_perf_s is not None:
        end_s = start_ref_s + (trial.skip_perf_s - trial.start_perf_s) - skip_guard_s
    else:
        end_s = start_ref_s + 30.0 - skip_guard_s
        warnings.append("skip_event_missing")

    if search_start_s >= end_s:
        raise ValueError(
            f"Track {trial.track_index} has empty analysis window "
            f"({search_start_s:.3f} >= {end_s:.3f})"
        )

    times, rms = frame_rms(
        audio,
        sample_rate,
        search_start_s,
        end_s,
        float(config.get("rms_window_ms", 50)),
        float(config.get("rms_hop_ms", 10)),
    )
    if len(rms) == 0:
        raise ValueError(f"Track {trial.track_index} has no audio frames to analyze")

    median_rms = float(np.median(rms))
    peak_rms = float(np.max(rms))
    peak_ratio = peak_rms / max(median_rms, 1e-9)

    if mode == "onset":
        threshold = robust_threshold(rms[: max(5, min(len(rms), 100))], sigma=6.0)
        above = np.flatnonzero(rms >= threshold)
        anchor_index = int(above[0]) if len(above) else int(np.argmax(rms))
        if len(above) == 0:
            warnings.append("onset_fallback_to_peak")
    else:
        pick_ratio = float(config.get("peak_pick_ratio", 0.985))
        candidates = np.flatnonzero(rms >= peak_rms * pick_ratio)
        anchor_index = int(candidates[0]) if len(candidates) else int(np.argmax(rms))

    anchor_s = float(times[anchor_index])
    press_to_anchor_ms = (anchor_s - start_ref_s) * 1000.0
    anchor_after_start_s = anchor_s - start_ref_s

    if ref_source != "marker":
        warnings.append("no_marker_used")
    if anchor_after_start_s > float(config.get("manual_review_if_peak_after_s", 25.0)):
        warnings.append("late_anchor_manual_review")
    if peak_ratio < float(config.get("manual_review_if_peak_to_median_under", 3.0)):
        warnings.append("weak_peak_manual_review")
    if end_s - anchor_s < 1.0:
        warnings.append("anchor_near_skip_manual_review")

    return {
        "track_index": trial.track_index,
        "song_id": trial.song_id,
        "title": trial.title,
        "bpm": trial.bpm if trial.bpm is not None else "",
        "reference_source": ref_source,
        "start_reference_s": round(start_ref_s, 6),
        "search_start_s": round(search_start_s, 6),
        "analysis_end_s": round(end_s, 6),
        "countdown_end_s": round(countdown_end_s, 6)
        if countdown_end_s is not None
        else "",
        "countdown_method": countdown_method,
        "anchor_s": round(anchor_s, 6),
        "anchor_after_start_s": round(anchor_after_start_s, 6),
        "press_to_anchor_ms": round(press_to_anchor_ms, 3),
        "peak_rms": round(peak_rms, 8),
        "median_rms": round(median_rms, 8),
        "peak_to_median": round(peak_ratio, 3),
        "mode": mode,
        "warnings": "|".join(warnings),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze OBS recording and compute press-to-anchor delays."
    )
    parser.add_argument(
        "--config",
        default="measurement/config.example.json",
        help="Path to measurement config JSON.",
    )
    parser.add_argument("--recording", required=True, help="OBS recording path.")
    parser.add_argument("--events", required=True, help="events.jsonl from the run.")
    parser.add_argument("--out", help="Output CSV path. Defaults next to events.jsonl.")
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Keep extracted WAV next to output CSV.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config_path = Path(args.config).resolve()
    config = load_json(config_path)
    config_dir = config_path.parent
    analysis_config = config.get("analysis", {})

    recording = resolve_path(args.recording, Path.cwd())
    events_path = resolve_path(args.events, Path.cwd())
    out_path = (
        resolve_path(args.out, Path.cwd())
        if args.out
        else events_path.parent / "analysis.csv"
    )
    wav_path = out_path.with_suffix(".wav")

    sample_rate = int(analysis_config.get("sample_rate", 48000))
    extract_audio(recording, wav_path, sample_rate)
    audio, sample_rate = read_wav_mono(wav_path)

    events = load_events(events_path)
    trials = build_trials(events)
    if not trials:
        raise ValueError("No start_pressed events found.")

    recording_started = next(
        (event for event in events if event.get("event") == "recording_started"),
        None,
    )
    recording_start_perf_s = (
        float(recording_started["perf_s"]) if recording_started else None
    )

    marker_times = detect_marker_times(
        audio,
        sample_rate,
        config.get("marker", {}),
        analysis_config.get("marker_detection", {}),
    )
    references, sources = pair_start_references(
        trials,
        marker_times,
        recording_start_perf_s,
    )

    rows = [
        analyze_trial(audio, sample_rate, trial, start_ref, source, analysis_config)
        for trial, start_ref, source in zip(trials, references, sources)
    ]
    write_csv(out_path, rows)

    marker_count = sum(1 for source in sources if source == "marker")
    print(f"Analyzed {len(rows)} tracks.")
    print(f"Marker references used: {marker_count}/{len(rows)}.")
    print(f"Output: {out_path}")

    if not args.keep_wav:
        try:
            wav_path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
