# 这是项目 Mainithm 的 CLAUDE.md

## 此项目

Mainithm 是一个用于实现舞萌和中二节奏手台拼机的项目
目前完成的部分:
- MVP, 位于 controller/

正在做的部分
- 延迟的自动测量和数据库

## 项目目录
controller/文件夹中有可工作的MVP, 能够使舞萌和中二上的特定的一首乐曲(Tiamat)同步启动, 用了input director

backend/ 在服务器上运行的Django 后端项目
- Django 5.2.8 + DRF 3.17.1
- Django 项目配置: `backend/mainithm_backend/`
- DRF app: `backend/sync/`
- 目前的用途: 储存和管理Maimai 和Chunithm 的乐曲的按下开始键和音乐中的特征的时间差
- 增加新测量到的数据的API
- 给Web 前端用的API

frontend/ 计划中的基于Svelte 的WebUI

docs/ 文档

clients/ 延迟测量客户端和曲库生成工具
- 测量流水线: OCR 选歌 -> 开歌 -> OBS 录制 -> 离线音频分析 -> 输出 press-to-anchor 延迟
- 曲库生成: 从外部 API 拉取舞萌/中二歌曲数据, 生成共有曲目 CSV
- 有 Tkinter GUI (`measurement_app.py`) 和命令行两种使用方式
- 详细文档见 `clients/README.md`

```
Mainithm/
├── controller/
│   ├── syncstart.py     # 依赖配置好的input director 的MVP
│   └── requirements.txt
├── backend/             # Django REST API
│   ├── manage.py
│   ├── mainithm_backend/  # Django 项目配置
│   ├── sync/              # 管理时间差数据的DRF 应用
│   └── requirements.txt
├── clients/                              # 延迟测量客户端
│   ├── mai_delay_measure.py              # 舞萌测量主控: OCR选歌、键盘控制、OBS录制
│   ├── analyze_recording.py              # 离线分析OBS录像, 计算 press-to-anchor 延迟
│   ├── measurement_app.py                # Tkinter GUI, 整合测量和分析流程
│   ├── dt_measurement.py                 # 延迟测量核心函数 (WIP)
│   ├── dt_sample.py                      # 实时音频录制和 onset 检测 (librosa)
│   ├── generate_maimai_master_csv.py     # 从外部API生成舞萌Master谱面CSV
│   ├── generate_chunithm_songs_csv.py    # 从外部API生成中二全曲CSV
│   ├── generate_maimai_chunithm_shared_csv.py  # 生成两游戏共有曲目CSV
│   ├── config.example.json               # 测量配置模板
│   ├── shared_songs.example.csv          # 共有曲目CSV格式示例
│   ├── maimai_master_songs.csv           # 生成的舞萌曲库
│   ├── chunithm_songs.csv               # 生成的中二曲库
│   ├── maimai_chunithm_shared_songs.csv  # 生成的共有曲库
│   ├── shared_songs.csv                  # 测量用曲库 (从shared生成)
│   ├── temp.py                           # 临时: 列出音频设备
│   ├── README.md                         # 测量流水线详细文档
│   └── requirements.txt
├── frontend/            # 计划中的Svelte webUI
├── docs/
│   ├── explanation/
│   │   ├── Mainithm.md               # 开发日志
│   │   └── Mainithm_Roadmap_Phase1.md  # 本阶段开发路线
│   ├── howto/
│   └── reference/
│       └── song_csv_generators.md     # 曲库生成脚本的数据源和用法说明
├── .gitignore
└── CLAUDE.md
```

## 决策记录

### Busy-Wait for Timing Precision

`time.sleep()` on Windows has ~15ms jitter due to the OS scheduler. For rhythm game sync, even a few milliseconds of desync is audible. The busy-wait approach pegs the CPU but guarantees sub-millisecond accuracy.

### Two-Key Sequence Logic

Chunithm is started first (key `'z'`) because its boot-to-gameplay time is longer. Maimai (`'c'`) is triggered later by the exact offset difference so both games reach the gameplay state simultaneously.

### InputDirector Integration

The script sends keys through InputDirector (a KVM-over-LAN tool) to control separate arcade cabinets from one PC. Key presses are not sent to the local machine's focused window — they go to the InputDirector target machine.

## 运行项目

**Sync-start script:**
```bash
cd controller
python syncstart.py
```

**Django dev server:**
```bash
cd backend
python manage.py runserver
```

## 依赖项

每个部分有各自的requirements.txt

- `controller/requirements.txt`: pynput, pywin32
- `clients/requirements.txt`: pynput, sounddevice, librosa, numpy
- `backend/requirements.txt`: Django, djangorestframework

## Common Gotchas

1. 每次修改代码之后说 '喵'
2. 使用Svelte 时始终遵循Svelte 5 标准
