# Mainithm 舞萌延迟测量脚本

这个目录是一套独立的舞萌测量流水线，暂时不依赖 Django 后台。它先解决“批量开歌、录屏、跳过、记录时间点、离线分析”的核心问题，后续可以把结果导入主数据库。

## 推荐方案

推荐先使用“离线峰值锚点法”，也就是：

1. OBS 录完整个 99 track 的画面和音频。
2. 脚本在每次按下开始键时写入日志，并可选播放一个短促高频 marker 音作为录音里的时间标记。
3. 每首歌开歌后等待固定窗口，例如 30 秒，然后同时按下 `E+D+Q+A` 跳过。
4. 录完后离线抽取音频，剔除开头的 track start、开始音效、提示鼓点，再从正式歌曲窗口里找最高电平的第一个位置，作为该首歌的“共同音频锚点”。
5. 之后测中二时也用同一个逻辑。最终同步用的是：

```text
需要等待的时间 = 中二 press_to_anchor_ms - 舞萌 press_to_anchor_ms
```

这个锚点不一定是歌曲第一个声音，但只要舞萌和中二测的是同一首歌、同一段音频，锚点在歌曲内部的位置会互相抵消，比“检测第一个鼓点”更适合批量测量。

## 为什么暂不推荐实时首鼓点法

实时首鼓点法理论上最直观，但它要求录屏、音频监听、提示鼓点剔除、开歌判定全部在线运行。舞萌的提示鼓点会跟 BPM 和拍号变化，容易和歌曲第一个鼓点混在一起。除非后面接入稳定的实时音频输入和可视化校验，否则首版更容易在“看似自动，实际频繁误判”的地方卡住。

本目录里的分析脚本仍保留 `onset` 模式，用于后续实验。

## OCR 的定位

OCR 适合做“辅助定位”，不适合作为唯一真相。建议：

- 选歌界面按字母排序。
- 准备一份舞萌中二共有歌曲 CSV。
- OCR 只截取标题区域，用 EasyOCR 识别，配合别名和模糊匹配。
- 识别不到就按 `D` 到下一首，同时把原始 OCR 文本写日志，方便之后调 crop 和别名。
- 真正跑 99 track 前，先用 dry run 在选歌界面跑 20 到 50 次，只检查 OCR 命中率。

如果 OCR 在某些字体、日文标题或高亮 UI 上不稳，后续可以加“标题区域模板截图/图像哈希”作为第二判断。

## 文件

- `mai_delay_measure.py`：控制键盘、OCR 选歌、OBS 开停录制、逐首开歌和跳过。
- `analyze_recording.py`：从 OBS 视频里抽音频并按日志分析每首歌的锚点延迟。
- `config.example.json`：测量配置模板。
- `shared_songs.example.csv`：共有歌曲表格式示例。
- `requirements-measurement.txt`：测量脚本依赖。

## 典型流程

### 图形工具

现在可以优先使用图形工具，不用手动记命令。

1. 双击项目根目录的 `open_measurement_app.cmd`。
2. 点击“生成测量曲库”，它会从 `maimai_chunithm_shared_songs.csv` 生成测量专用的 `shared_songs.csv`。
3. 点击“检查环境”，确认依赖和 `ffmpeg` 状态。
4. 点击“开始试跑”，先确认 OCR 和切歌逻辑。
5. 点击“开始正式测量”。
6. 录完后在“录像分析”里选择 OBS 录像和 `events.jsonl`，点击“分析录像”。

窗口里的“连接 OBS”“启用 OCR”“播放 marker 音”会写入临时运行配置，不会改动 `config.example.json`。

### 命令行

以下命令默认在 `D:\zmk\Mainithm\Mainithm` 这个内层项目目录执行。

1. 在 OBS 里建好录制场景，确认能录到舞萌画面和音频。
2. 在 OBS 的 WebSocket 设置里启用服务端。OBS 28 以上已内置 obs-websocket。
3. 按实际屏幕调整 `config.example.json` 里的 `ocr.title_region`。
4. 准备共有歌曲表，字段至少包含 `id,title,aliases,bpm`。
5. 先 dry run，只验证 OCR 和切歌逻辑：

```powershell
python measurement\mai_delay_measure.py --config measurement\config.example.json --dry-run
```

6. 正式采集：

```powershell
python measurement\mai_delay_measure.py --config measurement\config.example.json
```

7. 录完后分析：

```powershell
python measurement\analyze_recording.py --config measurement\config.example.json --recording "D:\OBS\mai_run.mkv" --events measurement\runs\你的run目录\events.jsonl
```

## 调参重点

- `ocr.title_region`：只框住歌名，不要框到难度、版本、曲师。
- `ocr.min_match_score`：OCR 错字多就降到 75 左右，误命中多就升到 88 以上。
- `timing.song_play_window_s`：默认 30 秒。如果很多歌前 30 秒都很弱，可以提高到 45 秒，但整轮更慢。
- `analysis.ignore_after_start_s`：保底忽略开歌后的 UI 音效和提示鼓点。
- `analysis.countdown_search_*`：用于自动寻找提示鼓点结束位置。
- `marker.enabled`：建议开启，并让 OBS 录到这个 marker 音。它能减少 OBS 开始录制时间和脚本时间之间的对齐误差。
