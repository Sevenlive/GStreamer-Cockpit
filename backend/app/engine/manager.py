"""Central EngineManager orchestrating virtual channels, persistence, and runners."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..models import (
    ChannelSnapshot,
    ChannelState,
    ChannelTelemetry,
    ConnectorEdge,
    ConnectorNode,
    EngineStatus,
    Position,
    VirtualChannel,
    model_to_dict,
    utc_now_iso,
)
from ..pipeline_builder import CompiledPipeline, compile_channel_pipeline
from ..registry import get_connector_definition
from .base import ChannelRunner
from .gst_runner import GST_AVAILABLE, GST_VERSION, GstChannelRunner
from .sim_runner import SimChannelRunner


def _make_preset_graph(preset: str, channel_name: str) -> tuple[List[ConnectorNode], List[ConnectorEdge]]:
    if preset == "test_record":
        nodes = [
            ConnectorNode(
                id="in_test",
                type="videotestsrc",
                label="SMPTE Color Bars",
                params={"pattern": "smpte", "width": 1280, "height": 720, "framerate": 30, "is_live": True},
                position=Position(x=60, y=140),
            ),
            ConnectorNode(
                id="tr_overlay",
                type="text_overlay",
                label="Studio Bug & TC",
                params={
                    "text": f"LIVE • {channel_name}",
                    "font_desc": "Sans Bold, 24",
                    "valignment": "top",
                    "halignment": "left",
                    "shaded_background": True,
                    "timecode_mode": "running-time",
                    "timecode_prefix": "TC ",
                    "timecode_format": "%Y-%m-%d %H:%M:%S",
                    "timecode_font_desc": "Monospace Bold, 18",
                    "timecode_valignment": "bottom",
                    "timecode_halignment": "right",
                    "timecode_shaded": True,
                },
                position=Position(x=360, y=140),
            ),
            ConnectorNode(
                id="out_preview",
                type="web_preview",
                label="Cockpit Monitor",
                params={"width": 640, "fps": 10, "quality": 75},
                position=Position(x=690, y=50),
            ),
            ConnectorNode(
                id="out_rec",
                type="file_record",
                label="Archive MP4",
                params={
                    "filename": "studio_ch01.mp4",
                    "container": "mp4",
                    "video_codec": "h264",
                    "bitrate_kbps": 4500,
                    "speed_preset": "veryfast",
                    "segment_seconds": 0,
                },
                position=Position(x=690, y=240),
            ),
        ]
        edges = [
            ConnectorEdge(id="e1", source="in_test", source_handle="out", target="tr_overlay", target_handle="in"),
            ConnectorEdge(id="e2", source="tr_overlay", source_handle="out", target="out_preview", target_handle="in"),
            ConnectorEdge(id="e3", source="tr_overlay", source_handle="out", target="out_rec", target_handle="in"),
        ]
        return nodes, edges

    if preset == "rtsp_rtmp":
        nodes = [
            ConnectorNode(
                id="in_rtsp",
                type="rtsp_ingest",
                label="Studio Cam 01 (RTSP)",
                params={"location": "rtsp://192.168.1.50:554/stream1", "protocols": "tcp", "latency": 200},
                position=Position(x=60, y=140),
            ),
            ConnectorNode(
                id="tr_scale",
                type="video_scale",
                label="Normalize 1080p30",
                params={"width": 1920, "height": 1080, "framerate": 30, "method": "bilinear"},
                position=Position(x=370, y=140),
            ),
            ConnectorNode(
                id="out_rtmp",
                type="rtmp_output",
                label="YouTube Live Push",
                params={
                    "location": "rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY",
                    "bitrate_kbps": 4500,
                    "keyframe_interval": 60,
                    "speed_preset": "veryfast",
                },
                position=Position(x=700, y=60),
            ),
            ConnectorNode(
                id="out_preview",
                type="web_preview",
                label="Confidence Monitor",
                params={"width": 640, "fps": 8, "quality": 70},
                position=Position(x=700, y=240),
            ),
        ]
        edges = [
            ConnectorEdge(id="e1", source="in_rtsp", source_handle="out", target="tr_scale", target_handle="in"),
            ConnectorEdge(id="e2", source="tr_scale", source_handle="out", target="out_rtmp", target_handle="in"),
            ConnectorEdge(id="e3", source="tr_scale", source_handle="out", target="out_preview", target_handle="in"),
        ]
        return nodes, edges

    if preset == "pip_switcher":
        nodes = [
            ConnectorNode(
                id="in_main",
                type="videotestsrc",
                label="Program Feed (Main)",
                params={"pattern": "smpte", "width": 1280, "height": 720, "framerate": 30, "is_live": True},
                position=Position(x=50, y=60),
            ),
            ConnectorNode(
                id="in_pip",
                type="videotestsrc",
                label="Guest Feed (PiP)",
                params={"pattern": "ball", "width": 640, "height": 360, "framerate": 30, "is_live": True},
                position=Position(x=50, y=250),
            ),
            ConnectorNode(
                id="tr_comp",
                type="compositor",
                label="PiP Compositor",
                params={
                    "output_width": 1280,
                    "output_height": 720,
                    "pip_x": 880,
                    "pip_y": 460,
                    "pip_width": 360,
                    "pip_height": 202,
                    "background": "black",
                },
                position=Position(x=380, y=140),
            ),
            ConnectorNode(
                id="out_srt",
                type="srt_output",
                label="SRT Contribution Out",
                params={"uri": "srt://127.0.0.1:9001", "mode": "caller", "latency": 125, "bitrate_kbps": 5000},
                position=Position(x=710, y=60),
            ),
            ConnectorNode(
                id="out_preview",
                type="web_preview",
                label="Multiview Preview",
                params={"width": 640, "fps": 10, "quality": 75},
                position=Position(x=710, y=240),
            ),
        ]
        edges = [
            ConnectorEdge(id="e1", source="in_main", source_handle="out", target="tr_comp", target_handle="in_0"),
            ConnectorEdge(id="e2", source="in_pip", source_handle="out", target="tr_comp", target_handle="in_1"),
            ConnectorEdge(id="e3", source="tr_comp", source_handle="out", target="out_srt", target_handle="in"),
            ConnectorEdge(id="e4", source="tr_comp", source_handle="out", target="out_preview", target_handle="in"),
        ]
        return nodes, edges

    return [], []


class EngineManager:
    """Manages VirtualChannel definitions, compilation, runners, and persistence."""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        recordings_dir: Optional[Path] = None,
        force_simulation: Optional[bool] = None,
    ) -> None:
        base_dir = Path(os.environ.get("COCKPIT_DATA_DIR", "data")).resolve()
        self.data_dir = (data_dir or base_dir).resolve()
        self.recordings_dir = (
            recordings_dir
            or Path(os.environ.get("COCKPIT_RECORDINGS_DIR", str(self.data_dir / "recordings")))
        ).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self.data_dir / "channels.json"

        env_sim = os.environ.get("COCKPIT_SIMULATION", "").lower() in ("1", "true", "yes")
        self._use_gstreamer = GST_AVAILABLE and not (force_simulation if force_simulation is not None else env_sim)

        self._lock = threading.RLock()
        self._channels: Dict[str, VirtualChannel] = {}
        self._runners: Dict[str, ChannelRunner] = {}
        self._compiled: Dict[str, CompiledPipeline] = {}
        self._run_ids: Dict[str, int] = {}
        self._listeners: List[Callable[[str, str], None]] = []

        self._load_or_seed()

    @property
    def backend_mode(self) -> str:
        return "gstreamer" if self._use_gstreamer else "simulation"

    def get_engine_status(self) -> EngineStatus:
        with self._lock:
            running = sum(
                1 for cid in self._channels
                if cid in self._runners and self._runners[cid].get_telemetry().state == ChannelState.RUNNING
            )
            return EngineStatus(
                backend_mode=self.backend_mode,
                gstreamer_version=GST_VERSION,
                total_channels=len(self._channels),
                running_channels=running,
                recordings_dir=str(self.recordings_dir),
            )

    def add_listener(self, fn: Callable[[str, str], None]) -> None:
        self._listeners.append(fn)

    def _notify(self, channel_id: str, event: str) -> None:
        for fn in list(self._listeners):
            try:
                fn(channel_id, event)
            except Exception:
                pass

    def _load_or_seed(self) -> None:
        if self._store_path.exists():
            try:
                raw = json.loads(self._store_path.read_text(encoding="utf-8"))
                for item in raw:
                    ch = VirtualChannel(**item)
                    self._channels[ch.id] = ch
                    self._compiled[ch.id] = compile_channel_pipeline(ch, self.recordings_dir)
                if self._channels:
                    return
            except Exception:
                pass

        # Seed default showcase virtual channels
        defaults = [
            ("ch-01", "CH-01 • Studio Test & Record", "SMPTE test source with live timecode overlay, browser preview, and MP4 recording.", "test_record"),
            ("ch-02", "CH-02 • RTSP Ingest to RTMP", "Pulls IP camera RTSP feed, normalizes to 1080p30, and pushes to RTMP + preview.", "rtsp_rtmp"),
            ("ch-03", "CH-03 • Dual-Source PiP Switcher", "Composites main program + PiP guest source and transmits via SRT + preview.", "pip_switcher"),
        ]
        for cid, name, desc, preset in defaults:
            nodes, edges = _make_preset_graph(preset, name)
            ch = VirtualChannel(id=cid, name=name, description=desc, nodes=nodes, edges=edges)
            self._channels[cid] = ch
            self._compiled[cid] = compile_channel_pipeline(ch, self.recordings_dir)
        self._persist()

    def _persist(self) -> None:
        payload = [model_to_dict(ch) for ch in self._channels.values()]
        tmp = self._store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._store_path)

    def _create_runner(self, channel: VirtualChannel, compiled: CompiledPipeline) -> ChannelRunner:
        if self._use_gstreamer:
            return GstChannelRunner(channel, compiled, on_event=self._notify)
        return SimChannelRunner(channel, compiled, on_event=self._notify)

    def list_snapshots(self) -> List[ChannelSnapshot]:
        with self._lock:
            return [self.get_snapshot(cid) for cid in self._channels]

    def get_snapshot(self, channel_id: str) -> ChannelSnapshot:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            ch = self._channels[channel_id]
            compiled = self._compiled.get(channel_id) or compile_channel_pipeline(ch, self.recordings_dir)
            runner = self._runners.get(channel_id)
            if runner is not None:
                telemetry = runner.get_telemetry()
                telemetry.run_id = self._run_ids.get(channel_id, 0)
                logs = runner.get_logs()
            else:
                telemetry = ChannelTelemetry(
                    state=ChannelState.STOPPED,
                    has_preview=len(compiled.preview_sink_names) > 0,
                    run_id=self._run_ids.get(channel_id, 0),
                )
                logs = []
            return ChannelSnapshot(
                channel=ch,
                telemetry=telemetry,
                pipeline_description=compiled.pipeline_description,
                validation_errors=compiled.validation_errors,
                recent_logs=logs,
            )

    def create_channel(self, name: str, description: str = "", preset: Optional[str] = None) -> ChannelSnapshot:
        with self._lock:
            cid = f"ch-{uuid.uuid4().hex[:6]}"
            nodes, edges = _make_preset_graph(preset or "blank", name)
            ch = VirtualChannel(id=cid, name=name, description=description, nodes=nodes, edges=edges)
            self._channels[cid] = ch
            self._compiled[cid] = compile_channel_pipeline(ch, self.recordings_dir)
            self._persist()
            self._notify(cid, "created")
            return self.get_snapshot(cid)

    def update_channel_meta(self, channel_id: str, name: Optional[str], description: Optional[str]) -> ChannelSnapshot:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            ch = self._channels[channel_id]
            if name is not None:
                ch.name = name
            if description is not None:
                ch.description = description
            ch.updated_at = utc_now_iso()
            self._persist()
            self._notify(channel_id, "updated")
            return self.get_snapshot(channel_id)

    def update_channel_graph(
        self,
        channel_id: str,
        nodes: List[ConnectorNode],
        edges: List[ConnectorEdge],
    ) -> ChannelSnapshot:
        from ..models import ConnectorCategory
        from ..registry import resolve_node_params

        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            ch = self._channels[channel_id]
            old_nodes = {n.id: n for n in ch.nodes}
            new_nodes = {n.id: n for n in nodes}
            old_edge_sigs = {(e.source, e.source_handle, e.target, e.target_handle) for e in ch.edges}
            new_edge_sigs = {(e.source, e.source_handle, e.target, e.target_handle) for e in edges}

            def _is_output(node: ConnectorNode) -> bool:
                d = get_connector_definition(node.type)
                return d is not None and d.category == ConnectorCategory.OUTPUT

            old_outputs = {nid: n for nid, n in old_nodes.items() if _is_output(n)}
            new_outputs = {nid: n for nid, n in new_nodes.items() if _is_output(n)}

            outputs_changed = set(old_outputs.keys()) != set(new_outputs.keys())
            source_changed = (
                (set(old_nodes.keys()) - set(old_outputs.keys()))
                != (set(new_nodes.keys()) - set(new_outputs.keys()))
                or old_edge_sigs != new_edge_sigs
            )
            live_updates: List[tuple[str, str, Any]] = []

            # Check output param changes (resolved against defaults, ignoring legacy keys)
            if not outputs_changed:
                for nid, new_n in new_outputs.items():
                    prev_n = old_outputs[nid]
                    if prev_n.type != new_n.type:
                        outputs_changed = True
                        break
                    defn = get_connector_definition(new_n.type)
                    live_keys = {p.name for p in defn.params if p.live_updatable} if defn else set()
                    old_p = resolve_node_params(prev_n.type, prev_n.params)
                    new_p = resolve_node_params(new_n.type, new_n.params)
                    for k in (p.name for p in (defn.params if defn else [])):
                        if old_p.get(k) != new_p.get(k):
                            if k in live_keys:
                                live_updates.append((nid, k, new_p.get(k)))
                            else:
                                outputs_changed = True
                                break
                    if outputs_changed:
                        break

            # Check source/transform param changes
            if not source_changed:
                for nid, new_n in new_nodes.items():
                    if nid in new_outputs:
                        continue
                    prev_n = old_nodes.get(nid)
                    if prev_n is None or prev_n.type != new_n.type:
                        source_changed = True
                        break
                    defn = get_connector_definition(new_n.type)
                    live_keys = {p.name for p in defn.params if p.live_updatable} if defn else set()
                    old_p = resolve_node_params(prev_n.type, prev_n.params)
                    new_p = resolve_node_params(new_n.type, new_n.params)
                    for k in (p.name for p in (defn.params if defn else [])):
                        if old_p.get(k) != new_p.get(k):
                            if k in live_keys:
                                live_updates.append((nid, k, new_p.get(k)))
                            else:
                                source_changed = True
                                break
                    if source_changed:
                        break

            ch.nodes = nodes
            ch.edges = edges
            ch.updated_at = utc_now_iso()
            compiled = compile_channel_pipeline(ch, self.recordings_dir)
            self._compiled[channel_id] = compiled
            self._persist()

            existing = self._runners.get(channel_id)
            if existing is not None and existing.get_telemetry().state == ChannelState.RUNNING:
                if not outputs_changed and not source_changed:
                    # Pure live-param / layout edit -> zero restart
                    existing.channel = ch
                    for nid, k, v in live_updates:
                        existing.update_live_param(nid, k, v)
                elif not outputs_changed and source_changed and compiled.is_valid:
                    # Only inputs/transforms changed -> hot-swap Stage 1 without restarting recording/outputs!
                    swapped = existing.hot_swap_source(ch, compiled)
                    if swapped:
                        for nid, k, v in live_updates:
                            if nid in new_outputs:
                                existing.update_live_param(nid, k, v)
                    else:
                        existing.stop()
                        self._run_ids[channel_id] = self._run_ids.get(channel_id, 0) + 1
                        runner = self._create_runner(ch, compiled)
                        self._runners[channel_id] = runner
                        runner.start()
                else:
                    # Outputs themselves changed -> full restart
                    existing.stop()
                    if compiled.is_valid:
                        self._run_ids[channel_id] = self._run_ids.get(channel_id, 0) + 1
                        runner = self._create_runner(ch, compiled)
                        self._runners[channel_id] = runner
                        runner.start()

            self._notify(channel_id, "graph_updated")
            return self.get_snapshot(channel_id)

    def update_node_params(
        self,
        channel_id: str,
        node_id: str,
        params: Dict[str, Any],
        label: Optional[str] = None,
    ) -> ChannelSnapshot:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            ch = self._channels[channel_id]
            target_node = next((n for n in ch.nodes if n.id == node_id), None)
            if target_node is None:
                raise KeyError(f"Node '{node_id}' not found in channel '{channel_id}'.")

            if label is not None:
                target_node.label = label
            target_node.params.update(params)
            ch.updated_at = utc_now_iso()
            self._compiled[channel_id] = compile_channel_pipeline(ch, self.recordings_dir)
            self._persist()

            # Apply live-updatable params immediately if channel is running
            runner = self._runners.get(channel_id)
            defn = get_connector_definition(target_node.type)
            if runner is not None and defn is not None:
                runner.channel = ch
                live_keys = {p.name for p in defn.params if p.live_updatable}
                for k, v in params.items():
                    if k in live_keys:
                        runner.update_live_param(node_id, k, v)

            self._notify(channel_id, "node_updated")
            return self.get_snapshot(channel_id)

    def delete_channel(self, channel_id: str) -> None:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            self.stop_channel(channel_id)
            self._channels.pop(channel_id, None)
            self._runners.pop(channel_id, None)
            self._compiled.pop(channel_id, None)
            self._run_ids.pop(channel_id, None)
            self._persist()
            self._notify(channel_id, "deleted")

    def start_channel(self, channel_id: str) -> ChannelSnapshot:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            ch = self._channels[channel_id]
            compiled = compile_channel_pipeline(ch, self.recordings_dir)
            self._compiled[channel_id] = compiled
            if not compiled.is_valid:
                raise ValueError("; ".join(compiled.validation_errors))

            existing = self._runners.get(channel_id)
            if existing is not None:
                existing.stop()

            self._run_ids[channel_id] = self._run_ids.get(channel_id, 0) + 1
            runner = self._create_runner(ch, compiled)
            self._runners[channel_id] = runner
            runner.start()
            self._notify(channel_id, "started")
            return self.get_snapshot(channel_id)

    def stop_channel(self, channel_id: str) -> ChannelSnapshot:
        with self._lock:
            if channel_id not in self._channels:
                raise KeyError(f"Channel '{channel_id}' not found.")
            runner = self._runners.get(channel_id)
            if runner is not None:
                runner.stop()
            self._notify(channel_id, "stopped")
            return self.get_snapshot(channel_id)

    def restart_channel(self, channel_id: str) -> ChannelSnapshot:
        with self._lock:
            self.stop_channel(channel_id)
            return self.start_channel(channel_id)

    def get_preview_frame(self, channel_id: str) -> Optional[bytes]:
        with self._lock:
            runner = self._runners.get(channel_id)
            if runner is None:
                return None
            return runner.get_latest_frame()

    def list_recordings(self) -> List[Dict[str, Any]]:
        files: List[Dict[str, Any]] = []
        if not self.recordings_dir.exists():
            return files
        for p in sorted(self.recordings_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_file():
                st = p.stat()
                files.append(
                    {
                        "name": p.name,
                        "size_bytes": st.st_size,
                        "modified_at": st.st_mtime,
                    }
                )
        return files

    def shutdown(self) -> None:
        with self._lock:
            for runner in list(self._runners.values()):
                try:
                    runner.stop()
                except Exception:
                    pass
