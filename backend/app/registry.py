"""Connector Registry defining all Input, Transform, and Output video connectors."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import ConnectorCategory, ConnectorDefinition, ParamOption, ParamSpec, PortSpec


def _build_registry() -> Dict[str, ConnectorDefinition]:
    defs: List[ConnectorDefinition] = [
        # ------------------------------------------------------------------
        # INPUT CONNECTORS
        # ------------------------------------------------------------------
        ConnectorDefinition(
            type="videotestsrc",
            label="Test Pattern Source",
            category=ConnectorCategory.INPUT,
            description="Generates synthetic broadcast test signals (SMPTE color bars, moving ball, snow, etc.).",
            gst_elements=["videotestsrc", "capsfilter"],
            inputs=[],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(
                    name="pattern",
                    label="Test Pattern",
                    type="select",
                    default="smpte",
                    live_updatable=True,
                    options=[
                        ParamOption(label="SMPTE Color Bars", value="smpte"),
                        ParamOption(label="SMPTE 100%", value="smpte100"),
                        ParamOption(label="Moving Ball", value="ball"),
                        ParamOption(label="Broadcast Snow", value="snow"),
                        ParamOption(label="Pinwheel", value="pinwheel"),
                        ParamOption(label="Circular", value="circular"),
                        ParamOption(label="Checkers 8px", value="checkers-8"),
                        ParamOption(label="Solid Black", value="black"),
                    ],
                ),
                ParamSpec(name="width", label="Width (px)", type="integer", default=1280, min=160, max=3840, step=16),
                ParamSpec(name="height", label="Height (px)", type="integer", default=720, min=120, max=2160, step=16),
                ParamSpec(name="framerate", label="Framerate (fps)", type="integer", default=30, min=1, max=120, step=1),
                ParamSpec(
                    name="is_live",
                    label="Live Clock Mode",
                    type="boolean",
                    default=True,
                    description="Synchronize buffer timestamps to real-time pipeline clock.",
                ),
            ],
        ),
        ConnectorDefinition(
            type="rtsp_ingest",
            label="RTSP Network Ingest",
            category=ConnectorCategory.INPUT,
            description="Pulls a live video stream from an IP camera, encoder, or RTSP server.",
            gst_elements=["rtspsrc", "decodebin"],
            inputs=[],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(
                    name="location",
                    label="RTSP URL",
                    type="string",
                    default="rtsp://127.0.0.1:8554/stream",
                    placeholder="rtsp://camera-ip:554/live",
                ),
                ParamSpec(
                    name="protocols",
                    label="Transport Protocol",
                    type="select",
                    default="tcp",
                    options=[
                        ParamOption(label="TCP (Interleaved)", value="tcp"),
                        ParamOption(label="UDP", value="udp"),
                        ParamOption(label="UDP Multicast", value="udp-mcast"),
                    ],
                ),
                ParamSpec(name="latency", label="Jitter Buffer (ms)", type="integer", default=200, min=0, max=5000, step=50),
                ParamSpec(name="user_id", label="Username", type="string", default="", placeholder="Optional"),
                ParamSpec(name="user_pw", label="Password", type="string", default="", placeholder="Optional"),
            ],
        ),
        ConnectorDefinition(
            type="srt_ingest",
            label="SRT Live Ingest",
            category=ConnectorCategory.INPUT,
            description="Low-latency Secure Reliable Transport (SRT) video receiver.",
            gst_elements=["srtsrc", "tsdemux", "decodebin"],
            inputs=[],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(
                    name="uri",
                    label="SRT URI",
                    type="string",
                    default="srt://0.0.0.0:9000",
                    placeholder="srt://0.0.0.0:9000?mode=listener",
                ),
                ParamSpec(
                    name="mode",
                    label="Connection Mode",
                    type="select",
                    default="listener",
                    options=[
                        ParamOption(label="Listener", value="listener"),
                        ParamOption(label="Caller", value="caller"),
                        ParamOption(label="Rendezvous", value="rendezvous"),
                    ],
                ),
                ParamSpec(name="latency", label="SRT Latency (ms)", type="integer", default=125, min=20, max=4000, step=25),
                ParamSpec(name="passphrase", label="Passphrase", type="string", default="", placeholder="Optional 10-79 chars"),
            ],
        ),
        ConnectorDefinition(
            type="rtmp_ingest",
            label="RTMP Stream Ingest",
            category=ConnectorCategory.INPUT,
            description="Receives a live RTMP feed from OBS, hardware encoders, or ingest relays.",
            gst_elements=["rtmp2src", "flvdemux", "decodebin"],
            inputs=[],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(
                    name="location",
                    label="RTMP URL",
                    type="string",
                    default="rtmp://127.0.0.1:1935/live/input",
                    placeholder="rtmp://host:1935/live/key",
                ),
                ParamSpec(name="timeout", label="Timeout (sec)", type="integer", default=10, min=1, max=120, step=1),
            ],
        ),
        ConnectorDefinition(
            type="uri_file_src",
            label="File / HTTP URI Source",
            category=ConnectorCategory.INPUT,
            description="Reads and decodes a local media file or HTTP/HLS stream via uridecodebin.",
            gst_elements=["uridecodebin"],
            inputs=[],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(
                    name="uri",
                    label="Media URI",
                    type="string",
                    default="file:///media/sample.mp4",
                    placeholder="file:///path/to/video.mp4 or https://...",
                ),
                ParamSpec(name="use_buffering", label="Network Buffering", type="boolean", default=False),
            ],
        ),
        # ------------------------------------------------------------------
        # TRANSFORM CONNECTORS
        # ------------------------------------------------------------------
        ConnectorDefinition(
            type="video_scale",
            label="Scale & Frame Rate",
            category=ConnectorCategory.TRANSFORM,
            description="Resizes resolution and normalizes frame rate with configurable scaling filter.",
            gst_elements=["videoscale", "videorate", "capsfilter"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(name="width", label="Target Width (px)", type="integer", default=1920, min=160, max=3840, step=16),
                ParamSpec(name="height", label="Target Height (px)", type="integer", default=1080, min=120, max=2160, step=16),
                ParamSpec(name="framerate", label="Target FPS", type="integer", default=30, min=1, max=120, step=1),
                ParamSpec(
                    name="method",
                    label="Scaling Method",
                    type="select",
                    default="bilinear",
                    options=[
                        ParamOption(label="Bilinear (Fast)", value="bilinear"),
                        ParamOption(label="Lanczos (Sharp)", value="lanczos"),
                        ParamOption(label="Nearest Neighbour", value="nearest-neighbour"),
                    ],
                ),
            ],
        ),
        ConnectorDefinition(
            type="text_overlay",
            label="Text & Timecode Overlay",
            category=ConnectorCategory.TRANSFORM,
            description="Burns channel branding text and optional running SMPTE timecode onto the video.",
            gst_elements=["textoverlay", "timeoverlay"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(name="text", label="Overlay Text", type="string", default="LIVE • CH-01", live_updatable=True),
                ParamSpec(name="font_desc", label="Font Description", type="string", default="Sans, 24", live_updatable=True),
                ParamSpec(
                    name="valignment",
                    label="Vertical Align",
                    type="select",
                    default="top",
                    live_updatable=True,
                    options=[
                        ParamOption(label="Top", value="top"),
                        ParamOption(label="Center", value="center"),
                        ParamOption(label="Bottom", value="bottom"),
                    ],
                ),
                ParamSpec(
                    name="halignment",
                    label="Horizontal Align",
                    type="select",
                    default="left",
                    live_updatable=True,
                    options=[
                        ParamOption(label="Left", value="left"),
                        ParamOption(label="Center", value="center"),
                        ParamOption(label="Right", value="right"),
                    ],
                ),
                ParamSpec(name="shaded_background", label="Shaded Box", type="boolean", default=True, live_updatable=True),
                ParamSpec(name="show_timecode", label="Burn Timecode", type="boolean", default=True),
            ],
        ),
        ConnectorDefinition(
            type="video_balance",
            label="Color Balance & Flip",
            category=ConnectorCategory.TRANSFORM,
            description="Adjusts brightness, contrast, saturation, hue, and orientation.",
            gst_elements=["videobalance", "videoflip"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[PortSpec(id="out", label="Video Out", media_type="video")],
            params=[
                ParamSpec(name="brightness", label="Brightness", type="number", default=0.0, min=-1.0, max=1.0, step=0.05, live_updatable=True),
                ParamSpec(name="contrast", label="Contrast", type="number", default=1.0, min=0.0, max=2.0, step=0.05, live_updatable=True),
                ParamSpec(name="saturation", label="Saturation", type="number", default=1.0, min=0.0, max=2.0, step=0.05, live_updatable=True),
                ParamSpec(name="hue", label="Hue", type="number", default=0.0, min=-1.0, max=1.0, step=0.05, live_updatable=True),
                ParamSpec(
                    name="flip_method",
                    label="Orientation",
                    type="select",
                    default="none",
                    options=[
                        ParamOption(label="None", value="none"),
                        ParamOption(label="Horizontal Flip", value="horizontal-flip"),
                        ParamOption(label="Vertical Flip", value="vertical-flip"),
                        ParamOption(label="Rotate 180°", value="rotate-180"),
                        ParamOption(label="Rotate 90° CW", value="clockwise"),
                        ParamOption(label="Rotate 90° CCW", value="counterclockwise"),
                    ],
                ),
            ],
        ),
        ConnectorDefinition(
            type="compositor",
            label="PiP Compositor",
            category=ConnectorCategory.TRANSFORM,
            description="Mixes a primary full-frame video source with a Picture-in-Picture secondary source.",
            gst_elements=["compositor"],
            inputs=[
                PortSpec(id="in_0", label="Main Video", media_type="video"),
                PortSpec(id="in_1", label="PiP Overlay", media_type="video"),
            ],
            outputs=[PortSpec(id="out", label="Mixed Out", media_type="video")],
            params=[
                ParamSpec(name="output_width", label="Canvas Width", type="integer", default=1280, min=320, max=3840, step=16),
                ParamSpec(name="output_height", label="Canvas Height", type="integer", default=720, min=240, max=2160, step=16),
                ParamSpec(name="pip_x", label="PiP X Offset", type="integer", default=880, min=0, max=3840, step=10),
                ParamSpec(name="pip_y", label="PiP Y Offset", type="integer", default=460, min=0, max=2160, step=10),
                ParamSpec(name="pip_width", label="PiP Width", type="integer", default=360, min=64, max=1920, step=8),
                ParamSpec(name="pip_height", label="PiP Height", type="integer", default=202, min=64, max=1080, step=8),
                ParamSpec(
                    name="background",
                    label="Background",
                    type="select",
                    default="black",
                    options=[
                        ParamOption(label="Black", value="black"),
                        ParamOption(label="Checkerboard", value="checker"),
                        ParamOption(label="White", value="white"),
                    ],
                ),
            ],
        ),
        # ------------------------------------------------------------------
        # OUTPUT CONNECTORS
        # ------------------------------------------------------------------
        ConnectorDefinition(
            type="file_record",
            label="File Recorder",
            category=ConnectorCategory.OUTPUT,
            description="Encodes and records video to MP4, MKV, or segmented MPEG-TS/MP4 chunks on disk.",
            gst_elements=["x264enc", "mp4mux", "filesink", "splitmuxsink"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[],
            params=[
                ParamSpec(name="filename", label="Output Filename", type="string", default="channel_recording.mp4", placeholder="studio_take.mp4"),
                ParamSpec(
                    name="container",
                    label="Container Format",
                    type="select",
                    default="mp4",
                    options=[
                        ParamOption(label="MP4 (.mp4)", value="mp4"),
                        ParamOption(label="Matroska (.mkv)", value="mkv"),
                        ParamOption(label="MPEG-TS (.ts)", value="ts"),
                    ],
                ),
                ParamSpec(
                    name="video_codec",
                    label="Video Codec",
                    type="select",
                    default="h264",
                    options=[
                        ParamOption(label="H.264 (x264enc)", value="h264"),
                        ParamOption(label="H.265 / HEVC (x265enc)", value="h265"),
                        ParamOption(label="VP8 (vp8enc)", value="vp8"),
                    ],
                ),
                ParamSpec(name="bitrate_kbps", label="Bitrate (kbps)", type="integer", default=4500, min=300, max=50000, step=100),
                ParamSpec(
                    name="speed_preset",
                    label="Encoder Preset",
                    type="select",
                    default="veryfast",
                    options=[
                        ParamOption(label="Ultrafast", value="ultrafast"),
                        ParamOption(label="Superfast", value="superfast"),
                        ParamOption(label="Veryfast", value="veryfast"),
                        ParamOption(label="Medium", value="medium"),
                    ],
                ),
                ParamSpec(
                    name="segment_seconds",
                    label="Segment Duration (s)",
                    type="integer",
                    default=0,
                    min=0,
                    max=3600,
                    step=10,
                    description="0 records a single file; >0 rotates files via splitmuxsink.",
                ),
            ],
        ),
        ConnectorDefinition(
            type="rtmp_output",
            label="RTMP Stream Push",
            category=ConnectorCategory.OUTPUT,
            description="Encodes H.264/FLV and pushes live to YouTube, Twitch, or an RTMP media server.",
            gst_elements=["x264enc", "flvmux", "rtmp2sink"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[],
            params=[
                ParamSpec(
                    name="location",
                    label="RTMP Destination URL",
                    type="string",
                    default="rtmp://127.0.0.1:1935/live/stream",
                    placeholder="rtmp://a.rtmp.youtube.com/live2/xxxx",
                ),
                ParamSpec(name="bitrate_kbps", label="Bitrate (kbps)", type="integer", default=3500, min=500, max=25000, step=100),
                ParamSpec(name="keyframe_interval", label="Keyframe Interval (frames)", type="integer", default=60, min=15, max=300, step=15),
                ParamSpec(
                    name="speed_preset",
                    label="Encoder Preset",
                    type="select",
                    default="veryfast",
                    options=[
                        ParamOption(label="Ultrafast", value="ultrafast"),
                        ParamOption(label="Superfast", value="superfast"),
                        ParamOption(label="Veryfast", value="veryfast"),
                    ],
                ),
            ],
        ),
        ConnectorDefinition(
            type="srt_output",
            label="SRT Stream Push",
            category=ConnectorCategory.OUTPUT,
            description="Encodes MPEG-TS and transmits over low-latency Secure Reliable Transport (SRT).",
            gst_elements=["x264enc", "mpegtsmux", "srtsink"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[],
            params=[
                ParamSpec(
                    name="uri",
                    label="SRT Destination URI",
                    type="string",
                    default="srt://127.0.0.1:9001",
                    placeholder="srt://receiver-ip:9001",
                ),
                ParamSpec(
                    name="mode",
                    label="Connection Mode",
                    type="select",
                    default="caller",
                    options=[
                        ParamOption(label="Caller", value="caller"),
                        ParamOption(label="Listener", value="listener"),
                        ParamOption(label="Rendezvous", value="rendezvous"),
                    ],
                ),
                ParamSpec(name="latency", label="SRT Latency (ms)", type="integer", default=125, min=20, max=4000, step=25),
                ParamSpec(name="bitrate_kbps", label="Bitrate (kbps)", type="integer", default=4000, min=500, max=30000, step=100),
            ],
        ),
        ConnectorDefinition(
            type="web_preview",
            label="Browser Live Preview",
            category=ConnectorCategory.OUTPUT,
            description="Streams low-latency MJPEG preview frames directly into the Cockpit web interface.",
            gst_elements=["videoscale", "videorate", "jpegenc", "appsink"],
            inputs=[PortSpec(id="in", label="Video In", media_type="video")],
            outputs=[],
            params=[
                ParamSpec(name="width", label="Preview Width (px)", type="integer", default=640, min=160, max=1280, step=16),
                ParamSpec(name="fps", label="Preview FPS", type="integer", default=10, min=1, max=30, step=1),
                ParamSpec(name="quality", label="JPEG Quality", type="integer", default=75, min=20, max=95, step=5),
            ],
        ),
    ]
    return {d.type: d for d in defs}


CONNECTOR_REGISTRY: Dict[str, ConnectorDefinition] = _build_registry()


def list_connector_definitions() -> List[ConnectorDefinition]:
    return list(CONNECTOR_REGISTRY.values())


def get_connector_definition(connector_type: str) -> Optional[ConnectorDefinition]:
    return CONNECTOR_REGISTRY.get(connector_type)


def resolve_node_params(connector_type: str, raw_params: Dict[str, Any]) -> Dict[str, Any]:
    """Merge connector defaults with node-specific parameter overrides."""
    defn = get_connector_definition(connector_type)
    if defn is None:
        return dict(raw_params)
    resolved: Dict[str, Any] = {p.name: p.default for p in defn.params}
    for key, value in raw_params.items():
        if value is not None:
            resolved[key] = value
    return resolved
