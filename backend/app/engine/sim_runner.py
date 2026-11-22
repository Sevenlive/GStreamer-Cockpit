"""Simulation pipeline runner used when GStreamer/PyGObject is not installed."""

from __future__ import annotations

import io
import math
import random
import threading
import time
from typing import Any, Callable, Dict, Optional

from PIL import Image, ImageDraw

from ..models import ChannelState, ChannelTelemetry, LogLevel, VirtualChannel
from ..pipeline_builder import CompiledPipeline
from ..registry import resolve_node_params
from .base import ChannelRunner

SMPTE_TOP = [
    (191, 191, 191),
    (191, 191, 0),
    (0, 191, 191),
    (0, 191, 0),
    (191, 0, 191),
    (191, 0, 0),
    (0, 0, 191),
]

SMPTE_MID = [
    (0, 0, 191),
    (19, 19, 19),
    (191, 0, 191),
    (19, 19, 19),
    (0, 191, 191),
    (19, 19, 19),
    (191, 191, 191),
]


class SimChannelRunner(ChannelRunner):
    """High-fidelity software simulator for development without GStreamer bindings."""

    def __init__(
        self,
        channel: VirtualChannel,
        compiled: CompiledPipeline,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        super().__init__(channel, compiled, on_event)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._latest_frame: Optional[bytes] = None
        self._frames_total = 0
        self._target_fps = self._infer_target_fps()
        self._target_bitrate = self._infer_target_bitrate()
        self._current_fps = 0.0
        self._current_bitrate = 0.0
        self._live_overrides: Dict[str, Dict[str, Any]] = {}

    def _infer_target_fps(self) -> float:
        for node in self.channel.nodes:
            if node.type in ("videotestsrc", "video_scale"):
                params = resolve_node_params(node.type, node.params)
                return float(params.get("framerate", 30))
        return 30.0

    def _infer_target_bitrate(self) -> float:
        total = 0.0
        for node in self.channel.nodes:
            if node.type in ("file_record", "rtmp_output", "srt_output"):
                params = resolve_node_params(node.type, node.params)
                total += float(params.get("bitrate_kbps", 3500))
        return total if total > 0 else 2800.0

    def _get_node_param(self, node_type: str, key: str, default: Any) -> Any:
        for node in self.channel.nodes:
            if node.type == node_type:
                override = self._live_overrides.get(node.id, {})
                if key in override:
                    return override[key]
                params = resolve_node_params(node.type, node.params)
                return params.get(key, default)
        return default

    def _has_node_type(self, node_type: str) -> bool:
        return any(n.type == node_type for n in self.channel.nodes)

    def start(self) -> None:
        if not self.compiled.is_valid:
            msg = "; ".join(self.compiled.validation_errors) or "Invalid pipeline"
            self._state = ChannelState.ERROR
            self._error_message = msg
            self._log(LogLevel.ERROR, "compiler", msg)
            raise ValueError(msg)

        if self._state == ChannelState.RUNNING:
            return

        self._stop_event.clear()
        self._error_message = None
        self._started_at = time.monotonic()
        self._state = ChannelState.RUNNING
        self._log(
            LogLevel.INFO,
            "sim-engine",
            f"Started simulated GStreamer pipeline ({self.compiled.active_output_count} active output(s)).",
        )
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"sim-ch-{self.channel.id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._started_at = None
            self._current_fps = 0.0
            self._current_bitrate = 0.0
            self._state = ChannelState.STOPPED
        self._log(LogLevel.INFO, "sim-engine", "Pipeline received EOS and transitioned to NULL.")

    def update_live_param(self, node_id: str, param_name: str, value: Any) -> bool:
        if self._state != ChannelState.RUNNING:
            return False
        with self._lock:
            self._live_overrides.setdefault(node_id, {})[param_name] = value
        self._log(LogLevel.INFO, f"node:{node_id}", f"Live updated {param_name}={value!r}")
        return True

    def hot_swap_source(self, channel: VirtualChannel, compiled: CompiledPipeline) -> bool:
        if self._state != ChannelState.RUNNING:
            return False
        with self._lock:
            self.channel = channel
            self.compiled = compiled
            self._target_fps = self._infer_target_fps()
        self._log(LogLevel.INFO, "sim-engine", "Hot-swapped ingest/transform stage without restarting outputs.")
        return True

    def _render_preview_frame(self, elapsed: float, frame_idx: int) -> bytes:
        w = int(self._get_node_param("web_preview", "width", 640))
        w = max(240, min(w, 960))
        src_w = int(self._get_node_param("video_scale", "width", self._get_node_param("videotestsrc", "width", 1280)))
        src_h = int(self._get_node_param("video_scale", "height", self._get_node_param("videotestsrc", "height", 720)))
        h = max(120, int(round(w * src_h / max(1, src_w))) // 2 * 2)
        self._preview_width = w
        self._preview_height = h
        quality = int(self._get_node_param("web_preview", "quality", 75))
        pattern = str(self._get_node_param("videotestsrc", "pattern", "smpte"))

        img = Image.new("RGB", (w, h), (16, 20, 26))
        draw = ImageDraw.Draw(img)

        if pattern == "ball":
            draw.rectangle([0, 0, w, h], fill=(14, 18, 24))
            # Subtle horizontal scan markers
            for y in range(0, h, 36):
                draw.line([(0, y), (w, y)], fill=(24, 30, 40), width=1)
            r = max(16, h // 9)
            cx = int(w * 0.5 + math.sin(elapsed * 2.1) * (w * 0.36))
            cy = int(h * 0.5 + math.cos(elapsed * 1.5) * (h * 0.30))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 185, 45), outline=(255, 255, 255), width=2)
        elif pattern == "black":
            draw.rectangle([0, 0, w, h], fill=(8, 10, 14))
        elif pattern == "checkers-8":
            step = max(16, w // 16)
            shift = int(elapsed * 20) % (step * 2)
            for yy in range(0, h, step):
                for xx in range(-step * 2, w + step, step):
                    if ((xx // step) + (yy // step)) % 2 == 0:
                        draw.rectangle([xx + shift, yy, xx + shift + step, yy + step], fill=(42, 50, 62))
        else:
            # Broadcast SMPTE bars + animated sweep bar
            top_h = int(h * 0.68)
            mid_h = int(h * 0.78)
            bar_w = w / 7.0
            for i, col in enumerate(SMPTE_TOP):
                draw.rectangle([int(i * bar_w), 0, int((i + 1) * bar_w), top_h], fill=col)
            for i, col in enumerate(SMPTE_MID):
                draw.rectangle([int(i * bar_w), top_h, int((i + 1) * bar_w), mid_h], fill=col)
            # Bottom pluge
            draw.rectangle([0, mid_h, w, h], fill=(18, 22, 28))
            draw.rectangle([0, mid_h, int(w * 0.2), h], fill=(0, 38, 76))
            draw.rectangle([int(w * 0.2), mid_h, int(w * 0.4), h], fill=(235, 235, 235))
            draw.rectangle([int(w * 0.4), mid_h, int(w * 0.6), h], fill=(48, 18, 96))

            # Animated broadcast motion marker so user sees live playback
            sweep_x = int((elapsed * 140) % w)
            draw.rectangle([sweep_x, mid_h + 4, (sweep_x + 28) % w, h - 4], fill=(34, 211, 238))

        def _safe_text(s: str) -> str:
            return s.replace("•", "|").encode("latin-1", "replace").decode("latin-1")

        # Picture-in-Picture overlay if compositor is present
        if self._has_node_type("compositor"):
            pw, ph = int(w * 0.30), int(h * 0.30)
            px, py = w - pw - 16, h - ph - 36
            draw.rectangle([px - 2, py - 2, px + pw + 2, py + ph + 2], fill=(245, 158, 11))
            draw.rectangle([px, py, px + pw, py + ph], fill=(16, 22, 32))
            br = max(8, ph // 5)
            bx = int(px + pw * 0.5 + math.cos(elapsed * 2.7) * (pw * 0.32))
            by = int(py + ph * 0.5 + math.sin(elapsed * 2.1) * (ph * 0.28))
            draw.ellipse([bx - br, by - br, bx + br, by + br], fill=(52, 211, 153))
            draw.text((px + 8, py + 6), "PIP | IN_1", fill=(230, 236, 242))

        # Overlay text if text_overlay node exists
        if self._has_node_type("text_overlay"):
            overlay_text = _safe_text(str(self._get_node_param("text_overlay", "text", self.channel.name)))
            draw.rectangle([14, 14, min(w - 14, 14 + len(overlay_text) * 8 + 24), 42], fill=(10, 14, 19))
            draw.text((24, 22), overlay_text, fill=(245, 248, 250))

        # Live REC / SIM badge & SMPTE timecode HUD
        secs = int(elapsed)
        hrs = secs // 3600
        mins = (secs % 3600) // 60
        sec = secs % 60
        ff = int((elapsed - secs) * self._target_fps)
        tc = f"{hrs:02d}:{mins:02d}:{sec:02d}:{ff:02d}"

        draw.rectangle([w - 122, 14, w - 14, 38], fill=(12, 16, 22))
        draw.ellipse([w - 114, 21, w - 104, 31], fill=(239, 68, 68))
        draw.text((w - 98, 20), "SIM LIVE", fill=(240, 244, 248))

        draw.rectangle([w - 134, h - 30, w - 12, h - 10], fill=(10, 14, 19))
        draw.text((w - 124, h - 25), tc, fill=(52, 211, 153))

        draw.rectangle([12, h - 30, 220, h - 10], fill=(10, 14, 19))
        draw.text((20, h - 25), _safe_text(f"{self.channel.name[:24]} | #{frame_idx}"), fill=(203, 213, 225))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def _run_loop(self) -> None:
        preview_fps = float(self._get_node_param("web_preview", "fps", 8))
        preview_fps = max(1.0, min(preview_fps, 15.0))
        interval = 1.0 / preview_fps
        has_preview = len(self.compiled.preview_sink_names) > 0
        frame_tick = 0

        while not self._stop_event.is_set():
            loop_start = time.monotonic()
            elapsed = loop_start - (self._started_at or loop_start)
            frame_tick += 1

            with self._lock:
                self._frames_total = int(elapsed * self._target_fps)
                jitter_fps = random.uniform(-0.3, 0.3)
                jitter_br = random.uniform(-85.0, 85.0)
                self._current_fps = round(max(1.0, self._target_fps + jitter_fps), 1)
                self._current_bitrate = round(max(200.0, self._target_bitrate + jitter_br), 1)

            if has_preview:
                try:
                    jpeg_bytes = self._render_preview_frame(elapsed, self._frames_total)
                    with self._lock:
                        self._latest_frame = jpeg_bytes
                except Exception as exc:
                    self._log(LogLevel.WARNING, "sim-preview", f"Frame render error: {exc}")

            sleep_time = interval - (time.monotonic() - loop_start)
            if sleep_time > 0:
                self._stop_event.wait(timeout=sleep_time)

    def get_telemetry(self) -> ChannelTelemetry:
        with self._lock:
            uptime = (time.monotonic() - self._started_at) if self._started_at else 0.0
            return ChannelTelemetry(
                state=self._state,
                uptime_sec=round(uptime, 1),
                fps=self._current_fps if self._state == ChannelState.RUNNING else 0.0,
                bitrate_kbps=self._current_bitrate if self._state == ChannelState.RUNNING else 0.0,
                frames_processed=self._frames_total,
                dropped_frames=0,
                active_outputs=self.compiled.active_output_count if self._state == ChannelState.RUNNING else 0,
                has_preview=len(self.compiled.preview_sink_names) > 0,
                preview_width=getattr(self, "_preview_width", None),
                preview_height=getattr(self, "_preview_height", None),
                error_message=self._error_message,
            )

    def get_latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame
