from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from queue import Empty, Queue
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    X,
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    LabelFrame,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter.scrolledtext import ScrolledText


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
DEFAULT_CONFIG = APP_DIR / "config.example.json"
DEFAULT_SHARED_SOURCE = APP_DIR / "maimai_chunithm_shared_songs.csv"
DEFAULT_MEASURE_SONGS = APP_DIR / "shared_songs.csv"
RUNTIME_CONFIG = APP_DIR / "runtime_config.json"


def rel_to_app_dir(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_DIR))
    except ValueError:
        return str(path.resolve())


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def combine_aliases(*values: str) -> str:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        for alias in str(value or "").replace(";", "|").split("|"):
            text = " ".join(alias.split())
            key = text.casefold()
            if text and key not in seen:
                aliases.append(text)
                seen.add(key)
    return "|".join(aliases)


def build_measurement_song_csv(source_path: Path, target_path: Path) -> int:
    with source_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["id", "title", "aliases", "bpm", "artist", "level"],
        )
        writer.writeheader()
        for row in rows:
            title = row.get("曲名", "").strip()
            if not title:
                continue
            bpm = row.get("舞萌BPM") or row.get("中二BPM") or ""
            writer.writerow(
                {
                    "id": row.get("舞萌ID", "").strip() or title,
                    "title": title,
                    "aliases": combine_aliases(
                        row.get("舞萌别名", ""),
                        row.get("中二别名", ""),
                    ),
                    "bpm": bpm,
                    "artist": row.get("中二创作者", ""),
                    "level": row.get("舞萌谱面", ""),
                }
            )
    return len(rows)


def latest_events_file() -> Path | None:
    candidates = list((APP_DIR / "runs").glob("*/events.jsonl"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


class MeasurementApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Mainithm 延迟测量工具")
        self.root.geometry("980x720")
        self.root.minsize(860, 620)

        self.python = Path(sys.executable)
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: Queue[str] = Queue()

        self.config_path = StringVar(value=str(DEFAULT_CONFIG))
        self.shared_source_path = StringVar(value=str(DEFAULT_SHARED_SOURCE))
        self.songs_path = StringVar(value=str(DEFAULT_MEASURE_SONGS))
        self.recording_path = StringVar(value="")
        self.events_path = StringVar(value=str(latest_events_file() or ""))
        self.max_tracks = StringVar(value="")
        self.max_moves = StringVar(value="")
        self.ocr_enabled = BooleanVar(value=True)
        self.obs_enabled = BooleanVar(value=False)
        self.marker_enabled = BooleanVar(value=True)

        self._build_ui()
        self.root.after(100, self._drain_output)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self) -> None:
        top = Frame(self.root, padx=12, pady=10)
        top.pack(fill=X)

        Label(top, text="Mainithm 延迟测量工具", font=("Segoe UI", 15, "bold")).pack(
            anchor="w"
        )
        Label(
            top,
            text="按顺序：生成测量曲库 -> 试跑确认识别 -> 正式测量 -> 选择录像分析。",
            fg="#555555",
        ).pack(anchor="w", pady=(4, 0))

        files = LabelFrame(self.root, text="文件", padx=10, pady=8)
        files.pack(fill=X, padx=12, pady=(0, 8))
        self._file_row(files, "配置", self.config_path, self.choose_config, 0)
        self._file_row(files, "共同曲目表", self.shared_source_path, self.choose_shared_source, 1)
        self._file_row(files, "测量曲库", self.songs_path, self.choose_songs, 2)

        options = LabelFrame(self.root, text="测量选项", padx=10, pady=8)
        options.pack(fill=X, padx=12, pady=(0, 8))
        Label(options, text="最多测几首").grid(row=0, column=0, sticky="w")
        Entry(options, textvariable=self.max_tracks, width=10).grid(row=0, column=1, sticky="w")
        Label(options, text="最多移动几次").grid(row=0, column=2, sticky="w", padx=(18, 0))
        Entry(options, textvariable=self.max_moves, width=10).grid(row=0, column=3, sticky="w")
        Checkbutton(options, text="启用 OCR", variable=self.ocr_enabled).grid(
            row=0, column=4, sticky="w", padx=(18, 0)
        )
        Checkbutton(options, text="连接 OBS", variable=self.obs_enabled).grid(
            row=0, column=5, sticky="w", padx=(12, 0)
        )
        Checkbutton(options, text="播放 marker 音", variable=self.marker_enabled).grid(
            row=0, column=6, sticky="w", padx=(12, 0)
        )
        options.columnconfigure(7, weight=1)

        actions = Frame(self.root, padx=12)
        actions.pack(fill=X, pady=(0, 8))
        self._button(actions, "生成测量曲库", self.prepare_songs).pack(side=LEFT, padx=(0, 8))
        self._button(actions, "检查环境", self.check_environment).pack(side=LEFT, padx=(0, 8))
        self._button(actions, "开始试跑", lambda: self.start_measurement(True)).pack(
            side=LEFT, padx=(0, 8)
        )
        self._button(actions, "开始正式测量", lambda: self.start_measurement(False)).pack(
            side=LEFT, padx=(0, 8)
        )
        self._button(actions, "停止当前任务", self.stop_process).pack(side=RIGHT)

        analysis = LabelFrame(self.root, text="录像分析", padx=10, pady=8)
        analysis.pack(fill=X, padx=12, pady=(0, 8))
        self._file_row(analysis, "录像文件", self.recording_path, self.choose_recording, 0)
        self._file_row(analysis, "事件日志", self.events_path, self.choose_events, 1)
        Button(analysis, text="使用最新日志", command=self.use_latest_events).grid(
            row=1, column=3, padx=(8, 0), sticky="e"
        )
        Button(analysis, text="分析录像", command=self.start_analysis).grid(
            row=2, column=3, padx=(8, 0), pady=(6, 0), sticky="e"
        )
        analysis.columnconfigure(1, weight=1)

        log_frame = LabelFrame(self.root, text="运行日志", padx=8, pady=8)
        log_frame.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))
        self.log = ScrolledText(log_frame, height=18, wrap="word")
        self.log.pack(fill=BOTH, expand=True)
        self.log.configure(state="disabled")

    def _file_row(
        self,
        parent: LabelFrame,
        label: str,
        variable: StringVar,
        command,
        row: int,
    ) -> None:
        Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8)
        Button(parent, text="选择", command=command).grid(row=row, column=2, sticky="e")
        parent.columnconfigure(1, weight=1)

    def _button(self, parent: Frame, text: str, command) -> Button:
        return Button(parent, text=text, command=command, padx=10, pady=4)

    def choose_config(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=APP_DIR,
            title="选择配置文件",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.config_path.set(path)

    def choose_shared_source(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=APP_DIR,
            title="选择共同曲目表",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.shared_source_path.set(path)

    def choose_songs(self) -> None:
        path = filedialog.asksaveasfilename(
            initialdir=APP_DIR,
            title="选择测量曲库位置",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.songs_path.set(path)

    def choose_recording(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 OBS 录像",
            filetypes=[("Video", "*.mkv *.mp4 *.mov *.flv"), ("All files", "*.*")],
        )
        if path:
            self.recording_path.set(path)

    def choose_events(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=APP_DIR / "runs",
            title="选择 events.jsonl",
            filetypes=[("Event logs", "events.jsonl"), ("All files", "*.*")],
        )
        if path:
            self.events_path.set(path)

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(END, text)
        self.log.see(END)
        self.log.configure(state="disabled")

    def prepare_songs(self) -> None:
        try:
            count = build_measurement_song_csv(
                Path(self.shared_source_path.get()),
                Path(self.songs_path.get()),
            )
        except Exception as exc:
            messagebox.showerror("生成失败", str(exc))
            self.append_log(f"\n生成测量曲库失败：{exc}\n")
            return
        self.append_log(f"\n已生成测量曲库：{self.songs_path.get()}（{count} 首）\n")

    def build_runtime_config(self) -> Path:
        songs_path = Path(self.songs_path.get())
        if not songs_path.exists() and Path(self.shared_source_path.get()).exists():
            count = build_measurement_song_csv(
                Path(self.shared_source_path.get()),
                songs_path,
            )
            self.append_log(f"\n已自动生成测量曲库：{songs_path}（{count} 首）\n")

        config = load_json(Path(self.config_path.get()))
        config["songs_csv"] = rel_to_app_dir(songs_path)
        config["output_dir"] = "runs"
        config.setdefault("ocr", {})["enabled"] = bool(self.ocr_enabled.get())
        config.setdefault("obs", {})["enabled"] = bool(self.obs_enabled.get())
        config.setdefault("marker", {})["enabled"] = bool(self.marker_enabled.get())
        if self.max_tracks.get().strip():
            config["max_tracks"] = int(self.max_tracks.get().strip())
        if self.max_moves.get().strip():
            config["max_selection_moves"] = int(self.max_moves.get().strip())
        save_json(RUNTIME_CONFIG, config)
        return RUNTIME_CONFIG

    def check_environment(self) -> None:
        code = (
            "import importlib.util, shutil; "
            "mods=['numpy','rapidfuzz','pynput','mss','easyocr','obsws_python']; "
            "print('Python OK'); "
            "[print(m, 'OK' if importlib.util.find_spec(m) else 'MISSING') for m in mods]; "
            "print('ffmpeg', 'OK' if shutil.which('ffmpeg') else 'MISSING')"
        )
        self.start_process([str(self.python), "-c", code], "环境检查")

    def start_measurement(self, dry_run: bool) -> None:
        try:
            config_path = self.build_runtime_config()
        except Exception as exc:
            messagebox.showerror("配置失败", str(exc))
            return
        args = [
            str(self.python),
            str(APP_DIR / "mai_delay_measure.py"),
            "--config",
            str(config_path),
        ]
        if dry_run:
            args.append("--dry-run")
        self.start_process(args, "试跑" if dry_run else "正式测量")

    def use_latest_events(self) -> None:
        latest = latest_events_file()
        if latest is None:
            messagebox.showinfo("没有找到日志", "还没有找到 measurement/runs 里的 events.jsonl。")
            return
        self.events_path.set(str(latest))

    def start_analysis(self) -> None:
        recording = self.recording_path.get().strip()
        events = self.events_path.get().strip()
        if not recording or not Path(recording).exists():
            messagebox.showerror("缺少录像", "请先选择 OBS 录像文件。")
            return
        if not events or not Path(events).exists():
            messagebox.showerror("缺少日志", "请先选择 events.jsonl。")
            return
        try:
            config_path = self.build_runtime_config()
        except Exception as exc:
            messagebox.showerror("配置失败", str(exc))
            return
        args = [
            str(self.python),
            str(APP_DIR / "analyze_recording.py"),
            "--config",
            str(config_path),
            "--recording",
            recording,
            "--events",
            events,
        ]
        self.start_process(args, "录像分析")

    def start_process(self, args: list[str], name: str) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showwarning("已有任务", "当前还有任务在运行，请先停止或等待结束。")
            return
        self.append_log(f"\n=== {name}开始 ===\n")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self.process = subprocess.Popen(
            args,
            cwd=PROJECT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        threading.Thread(target=self._read_process_output, daemon=True).start()
        threading.Thread(target=self._watch_process, args=(name,), daemon=True).start()

    def _read_process_output(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(line)

    def _watch_process(self, name: str) -> None:
        assert self.process is not None
        code = self.process.wait()
        self.output_queue.put(f"=== {name}结束，退出码 {code} ===\n")

    def _drain_output(self) -> None:
        try:
            while True:
                self.append_log(self.output_queue.get_nowait())
        except Empty:
            pass
        self.root.after(100, self._drain_output)

    def stop_process(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.append_log("\n当前没有正在运行的任务。\n")
            return
        self.append_log("\n正在停止当前任务...\n")
        try:
            if os.name == "nt":
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self.process.terminate()
        except Exception:
            self.process.terminate()

    def close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("任务仍在运行", "当前任务还在运行，确定要退出吗？"):
                return
            self.stop_process()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    MeasurementApp().run()
