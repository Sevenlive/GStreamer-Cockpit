# GStreamer Cockpit

A broadcast-grade **Virtual Channel Streaming & Recording Engine** powered by **GStreamer 1.0** (`PyGObject` + `FastAPI`) and a **React + TypeScript + React Flow** web interface.

Create virtual channels composed of modular **Input**, **Transform**, and **Output** video connectors, wire them visually on a node graph canvas, inspect the compiled `gst-launch-1.0` pipeline, and monitor live video previews, telemetry, and bus logs in real time.

## Architecture

- **Backend (`backend/`)**: Python 3.11, FastAPI, WebSockets, and `PyGObject` (`gi.repository.Gst`).
  - **Connector Registry (`app/registry.py`)**: Schema-driven catalog of 13 built-in connectors:
    - **Inputs**: Test Pattern (`videotestsrc`), RTSP Network Ingest (`rtspsrc`), SRT Live Ingest (`srtsrc`), RTMP Stream Ingest (`rtmp2src`), File / HTTP URI Source (`uridecodebin`).
    - **Transforms**: Scale & Frame Rate (`videoscale`/`videorate`), Text & Timecode Overlay (`textoverlay`/`timeoverlay`), Color Balance & Flip (`videobalance`/`videoflip`), PiP Compositor (`compositor`).
    - **Outputs**: File Recorder (`x264enc`/`x265enc`/`vp8enc` + `mp4mux`/`matroskamux`/`mpegtsmux` + `filesink`/`splitmuxsink`), RTMP Stream Push (`rtmp2sink`), SRT Stream Push (`srtsink`), Browser Live Preview (`jpegenc ! appsink` -> MJPEG).
  - **DAG Pipeline Compiler (`app/pipeline_builder.py`)**: Validates graphs (acyclic check, port rules, reachability) and compiles fan-out (`tee` + `queue leaky=downstream`) and multi-input (`compositor`) graphs into runnable GStreamer pipelines.
  - **Dual Execution Engine (`app/engine/`)**:
    - **Native GStreamer Runner (`gst_runner.py`)**: Runs real `Gst.Pipeline` instances on a background `GLib.MainLoop` with buffer pad probes (FPS/bitrate), `appsink` MJPEG live preview, graceful EOS shutdown (for valid MP4/MKV headers), and hot live property updates.
    - **Simulation Runner (`sim_runner.py`)**: Automatically activates when GStreamer bindings are not installed locally, generating live animated SMPTE/PiP/timecode JPEG preview frames and realistic telemetry for UI development.
- **Frontend (`frontend/`)**: React 18, TypeScript, Vite, `@xyflow/react`, and Vanilla CSS.
  - **Channel Dashboard**: Multi-channel broadcast multiview with live MJPEG monitors, start/stop/restart controls, FPS/bitrate/uptime telemetry, and signal-chain badges.
  - **Visual Node Graph Editor**: Interactive React Flow canvas with Connector Library, schema-driven Inspector (with live-updatable properties), and a bottom drawer for the compiled `gst-launch-1.0` command, live monitor, and GStreamer bus logs.

## Quick Start (Docker — Native GStreamer)

```bash
docker compose up --build
```

- Web Cockpit UI: `http://localhost:5173`
- FastAPI Engine & OpenAPI Docs: `http://localhost:8000/docs`
- Recorded files are written to `./recordings/`

## Local Development (Without Docker)

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

> If `python3-gi` and GStreamer 1.0 are installed on your host, the engine automatically uses **Native GStreamer** mode. Otherwise it seamlessly runs in **Simulation Engine** mode.

Run backend tests:

```bash
cd backend
python3 -m unittest discover -s app/tests -v
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.
