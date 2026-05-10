# CLAUDE.md - Technical Notes for Mainithm

This file contains technical details, architectural decisions, and important implementation notes for future development sessions.

## Project Overview

Mainithm (Maimai + Chunithm) is a rhythm game sync-start utility. The core problem: two arcade rhythm games need to start at precisely the same time, but their attract screens and boot sequences have different timing offsets. The tool automates keypress sequences with sub-millisecond precision to synchronize them.

The project is in MVP stage. The `controller/syncstart.py` script is the only functional component. A Django REST backend (`backend/`) is scaffolded for a future API that manages timing measurement data.

## Architecture

### `controller/syncstart.py` — Core Logic

- Uses `pynput.keyboard` to simulate physical key presses
- Presses key `'z'` (Chunithm trigger) first, holds for ~20ms, then after a calculated delay presses key `'c'` (Maimai trigger)
- The delay between keys = `t_chunithm - t_maimai - 20ms`, where `t_chunithm` and `t_maimai` are the boot-to-gameplay timing offsets for each cabinet
- Uses **busy-wait loops** (CPU polling) instead of `time.sleep()` for precision — `sleep` has OS scheduler jitter of ~15ms on Windows, which is unacceptable for sync accuracy
- InputDirector integration: keys are sent via InputDirector to control multiple machines from one keyboard

### Django REST Backend (`backend/`)

- Django 5.2.8 + Django REST Framework 3.17.1
- Project config: `backend/mainithm_backend/`
- DRF app: `backend/sync/`
- Purpose: manage delta-t data (time between pressing game start and track starting) for both Maimai and Chunithm
- API to add new measurement data (from delay measurer clients)
- API to retrieve data (for the Svelte web UI)

### Frontend (planned)

- Svelte web UI in `frontend/` — later phase of development

### Project Structure

```
Mainithm/
├── controller/          # Hardware automation
│   ├── syncstart.py     # Keyboard sync-start script (working MVP)
│   └── requirements.txt
├── backend/             # Django REST API
│   ├── manage.py
│   ├── mainithm_backend/  # Django project config (settings, urls, wsgi, asgi)
│   ├── sync/              # DRF app for timing data
│   └── requirements.txt
├── clients/             # Measurement & automation clients
│   ├── dt_measurement.py    # Audio onset detection (librosa)
│   ├── arcade_controller.py # Arcade control + measurement flow
│   ├── data/                # CSV measurement output
│   └── requirements.txt
├── frontend/            # Svelte web UI (planned)
├── docs/
│   ├── explanation/
│   │   ├── Mainithm.md              # Development log
│   │   └── Mainithm_Roadmap_Phase1.md  # Phase 1 roadmap
│   ├── howto/
│   └── reference/
├── .gitignore
└── CLAUDE.md
```

## Key Design Decisions

### Busy-Wait for Timing Precision

`time.sleep()` on Windows has ~15ms jitter due to the OS scheduler. For rhythm game sync, even a few milliseconds of desync is audible. The busy-wait approach pegs the CPU but guarantees sub-millisecond accuracy.

### Two-Key Sequence Logic

Chunithm is started first (key `'z'`) because its boot-to-gameplay time is longer. Maimai (`'c'`) is triggered later by the exact offset difference so both games reach the gameplay state simultaneously.

### InputDirector Integration

The script sends keys through InputDirector (a KVM-over-LAN tool) to control separate arcade cabinets from one PC. Key presses are not sent to the local machine's focused window — they go to the InputDirector target machine.

## Running the Project

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

## Dependencies

Each component has its own `requirements.txt`:

- `controller/requirements.txt`: pynput, pywin32
- `clients/requirements.txt`: pynput, sounddevice, librosa, numpy
- `backend/requirements.txt`: Django, djangorestframework

## Common Gotchas

1. Timing constants are cabinet-specific — `t_chunithm` and `t_maimai` values in `syncstart.py` must be measured and calibrated per physical setup
2. Busy-wait pegs one CPU core — expected and intentional, do not replace with `sleep`
3. InputDirector must be running — the script assumes InputDirector is active and the target machines are connected; it will silently send keys to the wrong target otherwise
4. Windows only — `pywin32` and the InputDirector integration are Windows-specific
5. Say: 'Meow' everytime you finish editing code.
