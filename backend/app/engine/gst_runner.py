"""Real PyGObject (gi.repository.Gst) pipeline runner."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from ..models import ChannelState, ChannelTelemetry, LogLevel, VirtualChannel
from ..pipeline_builder import CompiledPipeline
from .base import ChannelRunner

GST_AVAILABLE = False
GST_VERSION: Optional[str] = None

try:
    import gi  # type: ignore

    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst  # type: ignore

    Gst.init(None)
    GST_AVAILABLE = True
    GST_VERSION = Gst.version_string()
except Exception:
    GLib = None  # type: ignore
    Gst = None  # type: ignore


_mainloop_lock = threading.Lock()
_mainloop_started = False
_mainloop: Any = None


def _ensure_glib_mainloop() -> None:
    global _mainloop_started, _mainloop
    if not GST_AVAILABLE:
        return
    with _mainloop_lock:
        if _mainloop_started:
            return
        _mainloop = GLib.MainLoop()
        t = threading.Thread(target=_mainloop.run, name="gst-glib-mainloop", daemon=True)
        t.start()
        _mainloop_started = True


class GstChannelRunner(ChannelRunner):
    """Executes a compiled GStreamer pipeline using PyGObject Gst.Pipeline."""

    def __init__(
        self,
        channel: VirtualChannel,
        compiled: CompiledPipeline,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        super().__init__(channel, compiled, on_event)
        self._pipeline: Any = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._latest_frame: Optional[bytes] = None
        self._frames_total = 0
        self._window_frames = 0
        self._window_bytes = 0
        self._window_start = time.monotonic()
        self._fps = 0.0
        self._bitrate_kbps = 0.0
        self._eos_event = threading.Event()

    def start(self) -> None:
        if not GST_AVAILABLE:
            raise RuntimeError("PyGObject / GStreamer 1.0 is not installed in this environment.")
        if not self.compiled.is_valid:
            msg = "; ".join(self.compiled.validation_errors) or "Invalid pipeline"
            self._state = ChannelState.ERROR
            self._error_message = msg
            self._log(LogLevel.ERROR, "compiler", msg)
            raise ValueError(msg)

        _ensure_glib_mainloop()
        launch_str = self.compiled.pipeline_description.replace("\\\n", " ")
        self._state = ChannelState.STARTING
        self._error_message = None
        self._eos_event.clear()
        self._log(LogLevel.INFO, "gst", f"Parsing pipeline ({len(self.channel.nodes)} connectors)...")

        try:
            pipeline = Gst.parse_launch(launch_str)
        except Exception as exc:
            self._state = ChannelState.ERROR
            self._error_message = str(exc)
            self._log(LogLevel.ERROR, "gst", f"Failed to parse pipeline: {exc}")
            raise

        self._pipeline = pipeline

        # Attach buffer telemetry probe
        if self.compiled.probe_element_name:
            probe_el = pipeline.get_by_name(self.compiled.probe_element_name)
            if probe_el is not None:
                src_pad = probe_el.get_static_pad("src")
                if src_pad is not None:
                    src_pad.add_probe(Gst.PadProbeType.BUFFER, self._on_buffer_probe)

        # Attach live MJPEG preview appsinks
        for sink_name in self.compiled.preview_sink_names:
            appsink = pipeline.get_by_name(sink_name)
            if appsink is not None:
                appsink.set_property("emit-signals", True)
                appsink.connect("new-sample", self._on_new_preview_sample)

        # Watch bus
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self._state = ChannelState.ERROR
            self._error_message = "Pipeline failed to transition to PLAYING state."
            self._log(LogLevel.ERROR, "gst", self._error_message)
            pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
            raise RuntimeError(self._error_message)

        self._started_at = time.monotonic()
        self._window_start = self._started_at
        self._state = ChannelState.RUNNING
        self._log(LogLevel.INFO, "gst", "Pipeline PLAYING.")

    def stop(self) -> None:
        pipeline = self._pipeline
        if pipeline is None:
            self._state = ChannelState.STOPPED
            return

        self._log(LogLevel.INFO, "gst", "Sending EOS for graceful shutdown...")
        try:
            pipeline.send_event(Gst.Event.new_eos())
            self._eos_event.wait(timeout=1.5)
        except Exception:
            pass

        try:
            bus = pipeline.get_bus()
            if bus is not None:
                bus.remove_signal_watch()
            pipeline.set_state(Gst.State.NULL)
        finally:
            self._pipeline = None
            self._started_at = None
            self._fps = 0.0
            self._bitrate_kbps = 0.0
            self._state = ChannelState.STOPPED
            self._log(LogLevel.INFO, "gst", "Pipeline STOPPED.")

    def _on_buffer_probe(self, _pad: Any, info: Any) -> Any:
        buf = info.get_buffer()
        now = time.monotonic()
        with self._lock:
            self._frames_total += 1
            self._window_frames += 1
            if buf is not None:
                self._window_bytes += buf.get_size()
            elapsed = now - self._window_start
            if elapsed >= 1.0:
                self._fps = round(self._window_frames / elapsed, 1)
                self._bitrate_kbps = round((self._window_bytes * 8.0) / (elapsed * 1000.0), 1)
                self._window_frames = 0
                self._window_bytes = 0
                self._window_start = now
        return Gst.PadProbeReturn.OK

    def _on_new_preview_sample(self, appsink: Any) -> Any:
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK
        buf = sample.get_buffer()
        if buf is None:
            return Gst.FlowReturn.OK
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if ok:
            try:
                with self._lock:
                    self._latest_frame = bytes(map_info.data)
            finally:
                buf.unmap(map_info)
        return Gst.FlowReturn.OK

    def _on_bus_message(self, _bus: Any, message: Any) -> None:
        mtype = message.type
        src_name = message.src.get_name() if message.src else "bus"
        if mtype == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self._state = ChannelState.ERROR
            self._error_message = str(err)
            self._log(LogLevel.ERROR, src_name, f"{err} ({debug})")
        elif mtype == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            self._log(LogLevel.WARNING, src_name, f"{warn}")
        elif mtype == Gst.MessageType.EOS:
            self._log(LogLevel.INFO, src_name, "End-of-stream reached.")
            self._eos_event.set()
        elif mtype == Gst.MessageType.STATE_CHANGED and message.src == self._pipeline:
            old_s, new_s, _ = message.parse_state_changed()
            self._log(
                LogLevel.DEBUG,
                "pipeline",
                f"State changed: {old_s.value_nick} -> {new_s.value_nick}",
            )

    def update_live_param(self, node_id: str, param_name: str, value: Any) -> bool:
        if self._pipeline is None or self._state != ChannelState.RUNNING:
            return False
        el_name = self.compiled.node_element_names.get(node_id)
        if not el_name:
            return False
        element = self._pipeline.get_by_name(el_name)
        if element is None:
            return False
        gst_prop = param_name.replace("_", "-")
        try:
            element.set_property(gst_prop, value)
            self._log(LogLevel.INFO, el_name, f"Live updated {gst_prop}={value!r}")
            return True
        except Exception as exc:
            self._log(LogLevel.WARNING, el_name, f"Live update failed for {gst_prop}: {exc}")
            return False

    def get_telemetry(self) -> ChannelTelemetry:
        with self._lock:
            uptime = (time.monotonic() - self._started_at) if self._started_at else 0.0
            return ChannelTelemetry(
                state=self._state,
                uptime_sec=round(uptime, 1),
                fps=self._fps if self._state == ChannelState.RUNNING else 0.0,
                bitrate_kbps=self._bitrate_kbps if self._state == ChannelState.RUNNING else 0.0,
                frames_processed=self._frames_total,
                dropped_frames=0,
                active_outputs=self.compiled.active_output_count if self._state == ChannelState.RUNNING else 0,
                has_preview=len(self.compiled.preview_sink_names) > 0,
                error_message=self._error_message,
            )

    def get_latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame
