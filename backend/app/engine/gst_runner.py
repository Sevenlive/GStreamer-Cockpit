"""Real PyGObject (gi.repository.Gst) pipeline runner."""

from __future__ import annotations

import html
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
        self._source_pipeline: Any = None
        self._output_pipeline: Any = None
        self._lock = threading.Lock()
        self._started_at: Optional[float] = None
        self._latest_frame: Optional[bytes] = None
        self._preview_width: Optional[int] = None
        self._preview_height: Optional[int] = None
        self._frames_total = 0
        self._window_frames = 0
        self._window_bytes = 0
        self._window_start = time.monotonic()
        self._fps = 0.0
        self._bitrate_kbps = 0.0
        self._eos_event = threading.Event()

    def _get_element(self, name: str) -> Any:
        for pipe in (self._source_pipeline, self._output_pipeline, self._pipeline):
            if pipe is not None:
                el = pipe.get_by_name(name)
                if el is not None:
                    return el
        return None

    def _attach_probe(self, pipeline: Any, probe_name: Optional[str]) -> None:
        if not probe_name or pipeline is None:
            return
        probe_el = pipeline.get_by_name(probe_name)
        if probe_el is not None:
            src_pad = probe_el.get_static_pad("src")
            if src_pad is not None:
                src_pad.add_probe(Gst.PadProbeType.BUFFER, self._on_buffer_probe)

    def _attach_preview_sinks(self, pipeline: Any, sink_names: list[str]) -> None:
        if pipeline is None:
            return
        for sink_name in sink_names:
            appsink = pipeline.get_by_name(sink_name)
            if appsink is not None:
                appsink.set_property("emit-signals", True)
                appsink.connect("new-sample", self._on_new_preview_sample)

    def _attach_bus(self, pipeline: Any) -> None:
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)

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
        self._state = ChannelState.STARTING
        self._error_message = None
        self._eos_event.clear()

        use_two_stage = bool(
            self.compiled.source_pipeline_description
            and self.compiled.output_pipeline_description
        )

        if use_two_stage:
            src_str = (self.compiled.source_pipeline_description or "").replace("\\\n", " ")
            out_str = (self.compiled.output_pipeline_description or "").replace("\\\n", " ")
            self._log(LogLevel.INFO, "gst", f"Starting 2-stage hot-swappable pipeline ({len(self.channel.nodes)} connectors)...")
            try:
                out_pipe = Gst.parse_launch(out_str)
                src_pipe = Gst.parse_launch(src_str)
            except Exception as exc:
                self._state = ChannelState.ERROR
                self._error_message = str(exc)
                self._log(LogLevel.ERROR, "gst", f"Failed to parse 2-stage pipeline: {exc}")
                raise

            self._output_pipeline = out_pipe
            self._source_pipeline = src_pipe
            self._attach_probe(src_pipe, self.compiled.probe_element_name)
            self._attach_preview_sinks(out_pipe, self.compiled.preview_sink_names)
            self._attach_bus(out_pipe)
            self._attach_bus(src_pipe)

            ret_out = out_pipe.set_state(Gst.State.PLAYING)
            ret_src = src_pipe.set_state(Gst.State.PLAYING)
            if ret_out == Gst.StateChangeReturn.FAILURE or ret_src == Gst.StateChangeReturn.FAILURE:
                self._state = ChannelState.ERROR
                self._error_message = "2-stage pipeline failed to transition to PLAYING state."
                self._log(LogLevel.ERROR, "gst", self._error_message)
                src_pipe.set_state(Gst.State.NULL)
                out_pipe.set_state(Gst.State.NULL)
                self._source_pipeline = None
                self._output_pipeline = None
                raise RuntimeError(self._error_message)
        else:
            launch_str = self.compiled.pipeline_description.replace("\\\n", " ")
            self._log(LogLevel.INFO, "gst", f"Parsing pipeline ({len(self.channel.nodes)} connectors)...")
            try:
                pipeline = Gst.parse_launch(launch_str)
            except Exception as exc:
                self._state = ChannelState.ERROR
                self._error_message = str(exc)
                self._log(LogLevel.ERROR, "gst", f"Failed to parse pipeline: {exc}")
                raise

            self._pipeline = pipeline
            self._attach_probe(pipeline, self.compiled.probe_element_name)
            self._attach_preview_sinks(pipeline, self.compiled.preview_sink_names)
            self._attach_bus(pipeline)

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

    def hot_swap_source(self, channel: VirtualChannel, compiled: CompiledPipeline) -> bool:
        """Hot-swap Stage 1 (inputs & transforms) while Stage 2 (recordings & streams) stays PLAYING."""
        if (
            not GST_AVAILABLE
            or self._state != ChannelState.RUNNING
            or self._output_pipeline is None
            or not compiled.source_pipeline_description
            or compiled.bus_channel != self.compiled.bus_channel
        ):
            return False

        new_src_str = compiled.source_pipeline_description.replace("\\\n", " ")
        self._log(LogLevel.INFO, "gst", "Hot-swapping ingest/transform stage (outputs & recordings uninterrupted)...")
        try:
            new_src_pipe = Gst.parse_launch(new_src_str)
        except Exception as exc:
            self._log(LogLevel.ERROR, "gst", f"Hot-swap parse failed: {exc}")
            return False

        old_src = self._source_pipeline
        if old_src is not None:
            try:
                bus = old_src.get_bus()
                if bus is not None:
                    bus.remove_signal_watch()
                old_src.set_state(Gst.State.NULL)
            except Exception:
                pass

        self.channel = channel
        self.compiled = compiled
        self._source_pipeline = new_src_pipe
        self._attach_probe(new_src_pipe, compiled.probe_element_name)
        self._attach_bus(new_src_pipe)

        ret = new_src_pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self._log(LogLevel.ERROR, "gst", "Hot-swapped source stage failed to enter PLAYING.")
            new_src_pipe.set_state(Gst.State.NULL)
            self._source_pipeline = None
            return False

        self._log(LogLevel.INFO, "gst", "Hot-swap complete — recording & stream outputs continued seamlessly.")
        return True

    def stop(self) -> None:
        if self._pipeline is None and self._output_pipeline is None and self._source_pipeline is None:
            self._state = ChannelState.STOPPED
            return

        self._log(LogLevel.INFO, "gst", "Sending EOS for graceful shutdown...")
        eos_target = self._output_pipeline or self._pipeline
        if eos_target is not None:
            try:
                eos_target.send_event(Gst.Event.new_eos())
                self._eos_event.wait(timeout=1.5)
            except Exception:
                pass

        try:
            for pipe in (self._source_pipeline, self._output_pipeline, self._pipeline):
                if pipe is not None:
                    bus = pipe.get_bus()
                    if bus is not None:
                        bus.remove_signal_watch()
                    pipe.set_state(Gst.State.NULL)
        finally:
            self._pipeline = None
            self._source_pipeline = None
            self._output_pipeline = None
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
        caps = sample.get_caps()
        frame_w: Optional[int] = None
        frame_h: Optional[int] = None
        if caps is not None and caps.get_size() > 0:
            struct = caps.get_structure(0)
            ok_w, w_val = struct.get_int("width")
            ok_h, h_val = struct.get_int("height")
            if ok_w and ok_h and w_val > 0 and h_val > 0:
                frame_w, frame_h = w_val, h_val
        buf = sample.get_buffer()
        if buf is None:
            return Gst.FlowReturn.OK
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if ok:
            try:
                with self._lock:
                    self._latest_frame = bytes(map_info.data)
                    if frame_w and frame_h:
                        self._preview_width = frame_w
                        self._preview_height = frame_h
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
        elif mtype == Gst.MessageType.STATE_CHANGED and message.src in (
            self._pipeline,
            self._source_pipeline,
            self._output_pipeline,
        ):
            old_s, new_s, _ = message.parse_state_changed()
            self._log(
                LogLevel.DEBUG,
                "pipeline",
                f"State changed: {old_s.value_nick} -> {new_s.value_nick}",
            )

    def update_live_param(self, node_id: str, param_name: str, value: Any) -> bool:
        if self._state != ChannelState.RUNNING:
            return False
        el_name = self.compiled.node_element_names.get(node_id)
        if not el_name:
            return False

        # Extract sanitized node suffix (e.g. "text_tr_overlay" -> "tr_overlay")
        sid = el_name.split("_", 1)[1] if "_" in el_name else el_name
        node = next((n for n in self.channel.nodes if n.id == node_id), None)

        try:
            # 1. Text & Timecode Overlay (text_<sid>, time_<sid>, clock_<sid>)
            if el_name.startswith("text_") and param_name.startswith("timecode_"):
                time_el = self._get_element(f"time_{sid}")
                clock_el = self._get_element(f"clock_{sid}")

                if param_name == "timecode_mode":
                    mode = str(value)
                    if time_el is not None:
                        time_el.set_property("silent", mode in ("off", "clock"))
                        if mode in ("running-time", "stream-time", "buffer-time"):
                            time_el.set_property("time-mode", mode)
                    if clock_el is not None:
                        clock_el.set_property("silent", mode != "clock")
                    self._log(LogLevel.INFO, f"time_{sid}", f"Live switched timecode_mode={mode!r}")
                    return True

                if param_name == "timecode_format":
                    if clock_el is not None:
                        clock_el.set_property("time-format", str(value))
                        self._log(LogLevel.INFO, f"clock_{sid}", f"Live updated time-format={value!r}")
                        return True
                    return False

                tc_prop_map = {
                    "timecode_prefix": "text",
                    "timecode_font_desc": "font-desc",
                    "timecode_valignment": "valignment",
                    "timecode_halignment": "halignment",
                    "timecode_shaded": "shaded-background",
                }
                gst_prop = tc_prop_map.get(param_name)
                if not gst_prop:
                    return False
                prop_val = value
                if gst_prop == "text" and isinstance(prop_val, str):
                    prop_val = html.escape(prop_val, quote=False)
                elif gst_prop == "font-desc" and isinstance(prop_val, str):
                    prop_val = prop_val.replace(",", "")
                updated_any = False
                for target_el in (time_el, clock_el):
                    if target_el is not None:
                        target_el.set_property(gst_prop, prop_val)
                        updated_any = True
                if updated_any:
                    self._log(LogLevel.INFO, f"time_{sid}", f"Live updated {gst_prop}={prop_val!r}")
                return updated_any

            # 2. Video Balance & Flip (bal_<sid>, flip_<sid>)
            if el_name.startswith("bal_") and param_name == "flip_method":
                flip_el = self._get_element(f"flip_{sid}")
                if flip_el is None:
                    return False
                flip_el.set_property("method", str(value))
                self._log(LogLevel.INFO, f"flip_{sid}", f"Live updated method={value!r}")
                return True

            # 3. PiP Compositor pad properties (comp_<sid>.sink_1)
            if el_name.startswith("comp_") and param_name in ("pip_x", "pip_y", "pip_width", "pip_height"):
                comp_el = self._get_element(el_name)
                if comp_el is None:
                    return False
                pad = comp_el.get_static_pad("sink_1")
                if pad is None:
                    return False
                pad_prop = {
                    "pip_x": "xpos",
                    "pip_y": "ypos",
                    "pip_width": "width",
                    "pip_height": "height",
                }[param_name]
                pad.set_property(pad_prop, int(value))
                self._log(LogLevel.INFO, f"{el_name}.sink_1", f"Live updated {pad_prop}={int(value)}")
                return True

            # 4. Video Scale live capsfilter update (caps_<sid>)
            if el_name.startswith("scale_") and param_name in ("width", "height", "framerate") and node is not None:
                caps_el = self._get_element(f"caps_{sid}")
                if caps_el is None:
                    return False
                w = int(value if param_name == "width" else node.params.get("width", 1920))
                h = int(value if param_name == "height" else node.params.get("height", 1080))
                fps = int(value if param_name == "framerate" else node.params.get("framerate", 30))
                caps_str = f"video/x-raw,width={w},height={h},framerate={fps}/1"
                caps_el.set_property("caps", Gst.Caps.from_string(caps_str))
                self._log(LogLevel.INFO, f"caps_{sid}", f"Live updated caps={caps_str}")
                return True

            # 5. Output Encoder live bitrate (enc_<sid>)
            if param_name == "bitrate_kbps":
                enc_el = self._get_element(f"enc_{sid}")
                if enc_el is None:
                    return False
                factory_name = enc_el.get_factory().get_name() if enc_el.get_factory() else ""
                if factory_name == "vp8enc":
                    enc_el.set_property("target-bitrate", int(value) * 1000)
                else:
                    enc_el.set_property("bitrate", int(value))
                self._log(LogLevel.INFO, f"enc_{sid}", f"Live updated bitrate={int(value)} kbps")
                return True

            # 6. Web Preview live JPEG quality (jpeg_<sid>)
            if el_name.startswith("preview_sink_") and param_name == "quality":
                jpeg_el = self._get_element(f"jpeg_{sid}")
                if jpeg_el is None:
                    return False
                jpeg_el.set_property("quality", int(value))
                self._log(LogLevel.INFO, f"jpeg_{sid}", f"Live updated quality={int(value)}")
                return True

            # 7. Default direct element property update (textoverlay, videobalance, videotestsrc, compositor background)
            element = self._get_element(el_name)
            if element is None:
                return False
            gst_prop = param_name.replace("_", "-")
            prop_val = value
            if gst_prop == "text" and isinstance(prop_val, str):
                prop_val = html.escape(prop_val, quote=False)
            elif gst_prop == "font-desc" and isinstance(prop_val, str):
                prop_val = prop_val.replace(",", "")
            element.set_property(gst_prop, prop_val)
            self._log(LogLevel.INFO, el_name, f"Live updated {gst_prop}={prop_val!r}")
            return True
        except Exception as exc:
            self._log(LogLevel.WARNING, el_name, f"Live update failed for {param_name}: {exc}")
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
                preview_width=self._preview_width if self._state == ChannelState.RUNNING else None,
                preview_height=self._preview_height if self._state == ChannelState.RUNNING else None,
                error_message=self._error_message,
            )

    def get_latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame
