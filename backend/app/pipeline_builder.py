"""Compiles a VirtualChannel connector DAG into a GStreamer pipeline description."""

from __future__ import annotations

import html
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import ConnectorCategory, ConnectorEdge, ConnectorNode, VirtualChannel
from .registry import get_connector_definition, resolve_node_params


@dataclass
class CompiledPipeline:
    pipeline_description: str
    validation_errors: List[str] = field(default_factory=list)
    preview_sink_names: List[str] = field(default_factory=list)
    probe_element_name: Optional[str] = None
    active_output_count: int = 0
    node_element_names: Dict[str, str] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0 and bool(self.pipeline_description.strip())


def _safe_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _gst_quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _bool_str(value: bool) -> str:
    return "true" if value else "false"


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename.strip()) or "recording.mp4"
    return re.sub(r"[^a-zA-Z0-9._-]", "_", base)


def _has_cycle(node_ids: Set[str], adj: Dict[str, List[str]]) -> bool:
    state: Dict[str, int] = {nid: 0 for nid in node_ids}  # 0=unvisited, 1=visiting, 2=done

    def dfs(u: str) -> bool:
        state[u] = 1
        for v in adj.get(u, []):
            if state.get(v, 0) == 1:
                return True
            if state.get(v, 0) == 0 and dfs(v):
                return True
        state[u] = 2
        return False

    for nid in node_ids:
        if state[nid] == 0:
            if dfs(nid):
                return True
    return False


def _build_node_snippet(
    node: ConnectorNode,
    recordings_dir: Path,
    attach_probe: bool,
    preview_sink_names: List[str],
    node_element_names: Dict[str, str],
) -> str:
    sid = _safe_id(node.id)
    params = resolve_node_params(node.type, node.params)
    t = node.type

    # ---------------- INPUTS ----------------
    if t == "videotestsrc":
        el_name = f"src_{sid}"
        node_element_names[node.id] = el_name
        w = int(params["width"])
        h = int(params["height"])
        fps = int(params["framerate"])
        is_live = _bool_str(bool(params["is_live"]))
        pattern = str(params["pattern"])
        parts = [
            f"videotestsrc name={el_name} is-live={is_live} pattern={pattern}",
            f"video/x-raw,width={w},height={h},framerate={fps}/1",
            "videoconvert",
        ]
        if attach_probe:
            parts.append("identity name=telemetry_probe")
        return " ! ".join(parts)

    if t == "rtsp_ingest":
        el_name = f"src_{sid}"
        node_element_names[node.id] = el_name
        loc = _gst_quote(str(params["location"]))
        latency = int(params["latency"])
        protocols = str(params["protocols"])
        extra = ""
        if params.get("user_id"):
            extra += f" user-id={_gst_quote(str(params['user_id']))}"
        if params.get("user_pw"):
            extra += f" user-pw={_gst_quote(str(params['user_pw']))}"
        parts = [
            f"rtspsrc name={el_name} location={loc} latency={latency} protocols={protocols}{extra}",
            "decodebin",
            "videoconvert",
        ]
        if attach_probe:
            parts.append("identity name=telemetry_probe")
        return " ! ".join(parts)

    if t == "srt_ingest":
        el_name = f"src_{sid}"
        node_element_names[node.id] = el_name
        uri = str(params["uri"])
        mode = str(params["mode"])
        latency = int(params["latency"])
        extra = f" latency={latency}"
        if params.get("passphrase"):
            extra += f" passphrase={_gst_quote(str(params['passphrase']))}"
        if "mode=" not in uri:
            sep = "&" if "?" in uri else "?"
            uri = f"{uri}{sep}mode={mode}"
        parts = [
            f"srtsrc name={el_name} uri={_gst_quote(uri)}{extra}",
            "tsdemux",
            "decodebin",
            "videoconvert",
        ]
        if attach_probe:
            parts.append("identity name=telemetry_probe")
        return " ! ".join(parts)

    if t == "rtmp_ingest":
        el_name = f"src_{sid}"
        node_element_names[node.id] = el_name
        loc = _gst_quote(str(params["location"]))
        timeout = int(params["timeout"])
        parts = [
            f"rtmp2src name={el_name} location={loc} timeout={timeout}",
            "flvdemux",
            "decodebin",
            "videoconvert",
        ]
        if attach_probe:
            parts.append("identity name=telemetry_probe")
        return " ! ".join(parts)

    if t == "uri_file_src":
        el_name = f"src_{sid}"
        node_element_names[node.id] = el_name
        uri = _gst_quote(str(params["uri"]))
        buffering = _bool_str(bool(params["use_buffering"]))
        parts = [
            f"uridecodebin name={el_name} uri={uri} use-buffering={buffering}",
            "videoconvert",
        ]
        if attach_probe:
            parts.append("identity name=telemetry_probe")
        return " ! ".join(parts)

    # ---------------- TRANSFORMS ----------------
    if t == "video_scale":
        el_name = f"scale_{sid}"
        node_element_names[node.id] = el_name
        w = int(params["width"])
        h = int(params["height"])
        fps = int(params["framerate"])
        method = str(params["method"])
        return (
            f"videoconvert ! videoscale name={el_name} method={method} ! "
            f"videorate ! "
            f"video/x-raw,width={w},height={h},framerate={fps}/1 ! "
            f"videoconvert"
        )

    if t == "text_overlay":
        el_name = f"text_{sid}"
        node_element_names[node.id] = el_name
        # GStreamer textoverlay parses Pango markup; unescaped &, <, > causes Pango to fail rendering
        text = _gst_quote(html.escape(str(params["text"]), quote=False))
        font_desc = _gst_quote(str(params.get("font_desc") or "DejaVu Sans Bold 24").replace(",", ""))
        valign = str(params["valignment"])
        halign = str(params["halignment"])
        shaded = _bool_str(bool(params["shaded_background"]))
        chain = [
            "videoconvert",
            "video/x-raw,format=I420",
            f"textoverlay name={el_name} text={text} font-desc={font_desc} "
            f"valignment={valign} halignment={halign} shaded-background={shaded} "
            f"xpad=16 ypad=12 silent=false",
        ]

        # Backward compatibility for saved channels using legacy show_timecode boolean
        tc_mode = str(params.get("timecode_mode", "running-time"))
        if "timecode_mode" not in node.params and "show_timecode" in node.params:
            tc_mode = "running-time" if bool(node.params["show_timecode"]) else "off"

        if tc_mode != "off":
            tc_font = _gst_quote(
                str(params.get("timecode_font_desc") or "DejaVu Sans Mono Bold 18").replace(",", "")
            )
            tc_valign = str(params.get("timecode_valignment", "bottom"))
            tc_halign = str(params.get("timecode_halignment", "right"))
            tc_shaded = _bool_str(bool(params.get("timecode_shaded", True)))
            tc_prefix = _gst_quote(html.escape(str(params.get("timecode_prefix", "TC ")), quote=False))

            if tc_mode == "clock":
                tc_fmt = _gst_quote(str(params.get("timecode_format", "%Y-%m-%d %H:%M:%S")))
                chain.append(
                    f"clockoverlay name=time_{sid} time-format={tc_fmt} text={tc_prefix} "
                    f"valignment={tc_valign} halignment={tc_halign} "
                    f"font-desc={tc_font} shaded-background={tc_shaded} xpad=16 ypad=12 silent=false"
                )
            else:
                chain.append(
                    f"timeoverlay name=time_{sid} time-mode={tc_mode} text={tc_prefix} "
                    f"valignment={tc_valign} halignment={tc_halign} "
                    f"font-desc={tc_font} shaded-background={tc_shaded} xpad=16 ypad=12 silent=false"
                )

        # Force plain video/x-raw without GstVideoOverlayCompositionMeta so text is always
        # blended directly into frame pixels before tee, videoscale, jpegenc, or encoders.
        chain.append("video/x-raw,format=I420")
        chain.append("videoconvert")
        return " ! ".join(chain)

    if t == "video_balance":
        el_name = f"bal_{sid}"
        node_element_names[node.id] = el_name
        brightness = float(params["brightness"])
        contrast = float(params["contrast"])
        saturation = float(params["saturation"])
        hue = float(params["hue"])
        flip = str(params["flip_method"])
        chain = [
            "videoconvert",
            f"videobalance name={el_name} brightness={brightness:.2f} "
            f"contrast={contrast:.2f} saturation={saturation:.2f} hue={hue:.2f}",
        ]
        if flip != "none":
            chain.append(f"videoflip name=flip_{sid} method={flip}")
        chain.append("videoconvert")
        return " ! ".join(chain)

    if t == "compositor":
        el_name = f"comp_{sid}"
        node_element_names[node.id] = el_name
        out_w = int(params["output_width"])
        out_h = int(params["output_height"])
        pip_x = int(params["pip_x"])
        pip_y = int(params["pip_y"])
        pip_w = int(params["pip_width"])
        pip_h = int(params["pip_height"])
        bg = str(params["background"])
        return (
            f"compositor name={el_name} background={bg} "
            f"sink_0::xpos=0 sink_0::ypos=0 sink_0::width={out_w} sink_0::height={out_h} "
            f"sink_1::xpos={pip_x} sink_1::ypos={pip_y} sink_1::width={pip_w} sink_1::height={pip_h} ! "
            f"video/x-raw,width={out_w},height={out_h} ! videoconvert"
        )

    # ---------------- OUTPUTS ----------------
    if t == "file_record":
        el_name = f"rec_{sid}"
        node_element_names[node.id] = el_name
        filename = _sanitize_filename(str(params["filename"]))
        container = str(params["container"])
        codec = str(params["video_codec"])
        bitrate = int(params["bitrate_kbps"])
        preset = str(params["speed_preset"])
        segment_sec = int(params["segment_seconds"])

        out_path = recordings_dir / filename
        if codec == "h264":
            enc = f"x264enc bitrate={bitrate} speed-preset={preset} tune=zerolatency ! h264parse"
        elif codec == "h265":
            enc = f"x265enc bitrate={bitrate} speed-preset={preset} ! h265parse"
        else:
            enc = f"vp8enc target-bitrate={bitrate * 1000}"

        mux_map = {"mp4": "mp4mux", "mkv": "matroskamux", "ts": "mpegtsmux"}
        mux = mux_map.get(container, "mp4mux")

        if segment_sec > 0:
            stem = out_path.stem
            ext = out_path.suffix or f".{container}"
            seg_pattern = str(recordings_dir / f"{stem}_%05d{ext}")
            max_size_ns = segment_sec * 1_000_000_000
            return (
                f"videoconvert ! {enc} ! "
                f"splitmuxsink name={el_name} location={_gst_quote(seg_pattern)} "
                f"muxer={mux} max-size-time={max_size_ns}"
            )
        return (
            f"videoconvert ! {enc} ! {mux} ! "
            f"filesink name={el_name} location={_gst_quote(str(out_path))}"
        )

    if t == "rtmp_output":
        el_name = f"rtmp_{sid}"
        node_element_names[node.id] = el_name
        loc = _gst_quote(str(params["location"]))
        bitrate = int(params["bitrate_kbps"])
        kf = int(params["keyframe_interval"])
        preset = str(params["speed_preset"])
        return (
            f"videoconvert ! "
            f"x264enc bitrate={bitrate} key-int-max={kf} speed-preset={preset} tune=zerolatency ! "
            f"h264parse ! flvmux streamable=true ! "
            f"rtmp2sink name={el_name} location={loc}"
        )

    if t == "srt_output":
        el_name = f"srt_{sid}"
        node_element_names[node.id] = el_name
        uri = str(params["uri"])
        mode = str(params["mode"])
        latency = int(params["latency"])
        bitrate = int(params["bitrate_kbps"])
        if "mode=" not in uri:
            sep = "&" if "?" in uri else "?"
            uri = f"{uri}{sep}mode={mode}"
        return (
            f"videoconvert ! "
            f"x264enc bitrate={bitrate} speed-preset=veryfast tune=zerolatency ! "
            f"h264parse ! mpegtsmux ! "
            f"srtsink name={el_name} uri={_gst_quote(uri)} latency={latency}"
        )

    if t == "web_preview":
        el_name = f"preview_sink_{sid}"
        node_element_names[node.id] = el_name
        preview_sink_names.append(el_name)
        width = max(160, int(params["width"]) // 2 * 2)
        height = max(90, int(round(width * 9 / 16)) // 2 * 2)
        fps = int(params["fps"])
        quality = int(params["quality"])
        return (
            f"videoconvert ! videoscale add-borders=true ! videorate ! "
            f"video/x-raw,width={width},height={height},pixel-aspect-ratio=1/1,framerate={fps}/1 ! "
            f"jpegenc quality={quality} ! "
            f"appsink name={el_name} emit-signals=true max-buffers=2 drop=true sync=false"
        )

    return f"identity name=unknown_{sid}"


def compile_channel_pipeline(
    channel: VirtualChannel,
    recordings_dir: Path,
) -> CompiledPipeline:
    """Validate and compile a VirtualChannel DAG into a GStreamer pipeline string."""
    errors: List[str] = []
    if not channel.nodes:
        return CompiledPipeline(
            pipeline_description="",
            validation_errors=["Channel has no connectors. Add at least one Input and one Output."],
        )

    node_map: Dict[str, ConnectorNode] = {}
    for node in channel.nodes:
        if node.id in node_map:
            errors.append(f"Duplicate connector node ID: {node.id}")
        defn = get_connector_definition(node.type)
        if defn is None:
            errors.append(f"Unknown connector type '{node.type}' on node '{node.label}'.")
        node_map[node.id] = node

    outgoing: Dict[str, List[ConnectorEdge]] = defaultdict(list)
    incoming: Dict[str, List[ConnectorEdge]] = defaultdict(list)
    adj: Dict[str, List[str]] = defaultdict(list)

    for edge in channel.edges:
        if edge.source not in node_map:
            errors.append(f"Edge '{edge.id}' references missing source node '{edge.source}'.")
            continue
        if edge.target not in node_map:
            errors.append(f"Edge '{edge.id}' references missing target node '{edge.target}'.")
            continue
        if edge.source == edge.target:
            errors.append(f"Self-loop detected on connector '{node_map[edge.source].label}'.")
            continue

        src_def = get_connector_definition(node_map[edge.source].type)
        tgt_def = get_connector_definition(node_map[edge.target].type)
        if src_def and src_def.category == ConnectorCategory.OUTPUT:
            errors.append(f"Output connector '{node_map[edge.source].label}' cannot feed downstream nodes.")
        if tgt_def and tgt_def.category == ConnectorCategory.INPUT:
            errors.append(f"Input connector '{node_map[edge.target].label}' cannot accept upstream connections.")

        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
        adj[edge.source].append(edge.target)

    if _has_cycle(set(node_map.keys()), adj):
        errors.append("Cycle detected in connector graph. Pipelines must be acyclic (DAG).")

    inputs = [
        n for n in channel.nodes
        if (d := get_connector_definition(n.type)) is not None and d.category == ConnectorCategory.INPUT
    ]
    outputs = [
        n for n in channel.nodes
        if (d := get_connector_definition(n.type)) is not None and d.category == ConnectorCategory.OUTPUT
    ]

    if not inputs:
        errors.append("Channel requires at least one Input connector.")
    if not outputs:
        errors.append("Channel requires at least one Output connector.")

    # Check reachability from inputs
    reachable: Set[str] = set()
    stack = [n.id for n in inputs]
    while stack:
        curr = stack.pop()
        if curr in reachable:
            continue
        reachable.add(curr)
        for nxt in adj.get(curr, []):
            stack.append(nxt)

    connected_outputs = [o for o in outputs if o.id in reachable]
    if outputs and not connected_outputs:
        errors.append("No Output connector is connected to an Input source.")

    if errors:
        return CompiledPipeline(
            pipeline_description="",
            validation_errors=errors,
        )

    # Identify multi-input nodes (e.g. compositor)
    multi_input_nodes: Set[str] = set()
    for node in channel.nodes:
        defn = get_connector_definition(node.type)
        if defn and len(defn.inputs) > 1:
            multi_input_nodes.add(node.id)

    preview_sink_names: List[str] = []
    node_element_names: Dict[str, str] = {}
    branches: List[str] = []
    emitted_multi: Set[str] = set()
    probe_attached = False

    def emit_from_node(node_id: str, prefix: str = "") -> None:
        nonlocal probe_attached
        node = node_map[node_id]
        defn = get_connector_definition(node.type)
        attach_probe = False
        if not probe_attached and defn and defn.category == ConnectorCategory.INPUT:
            attach_probe = True
            probe_attached = True

        snippet = _build_node_snippet(
            node=node,
            recordings_dir=recordings_dir,
            attach_probe=attach_probe,
            preview_sink_names=preview_sink_names,
            node_element_names=node_element_names,
        )
        chain_parts: List[str] = [prefix, snippet] if prefix else [snippet]

        curr_id = node_id
        while True:
            edges = outgoing.get(curr_id, [])
            if not edges:
                # Leaf node (output or dead-end transform)
                branches.append(" ! ".join(chain_parts))
                return

            if len(edges) == 1:
                edge = edges[0]
                target_id = edge.target
                if target_id in multi_input_nodes:
                    # Link into compositor sink pad
                    pad_idx = "1" if edge.target_handle == "in_1" else "0"
                    comp_name = f"comp_{_safe_id(target_id)}"
                    chain_parts.append(f"queue leaky=downstream max-size-buffers=4 ! {comp_name}.sink_{pad_idx}")
                    branches.append(" ! ".join(chain_parts))
                    if target_id not in emitted_multi:
                        emitted_multi.add(target_id)
                        emit_from_node(target_id)
                    return

                # Continue linear chain
                tgt_node = node_map[target_id]
                tgt_snippet = _build_node_snippet(
                    node=tgt_node,
                    recordings_dir=recordings_dir,
                    attach_probe=False,
                    preview_sink_names=preview_sink_names,
                    node_element_names=node_element_names,
                )
                chain_parts.append(tgt_snippet)
                curr_id = target_id
            else:
                # Fan-out via tee
                tee_name = f"tee_{_safe_id(curr_id)}"
                chain_parts.append(f"tee name={tee_name}")
                branches.append(" ! ".join(chain_parts))
                for edge in edges:
                    target_id = edge.target
                    branch_prefix = f"{tee_name}. ! queue leaky=downstream max-size-buffers=4"
                    if target_id in multi_input_nodes:
                        pad_idx = "1" if edge.target_handle == "in_1" else "0"
                        comp_name = f"comp_{_safe_id(target_id)}"
                        branches.append(f"{branch_prefix} ! {comp_name}.sink_{pad_idx}")
                        if target_id not in emitted_multi:
                            emitted_multi.add(target_id)
                            emit_from_node(target_id)
                    else:
                        emit_from_node(target_id, prefix=branch_prefix)
                return

    for inp in inputs:
        if outgoing.get(inp.id):
            emit_from_node(inp.id)

    pipeline_str = " \\\n  ".join(branches)
    return CompiledPipeline(
        pipeline_description=pipeline_str,
        validation_errors=[],
        preview_sink_names=preview_sink_names,
        probe_element_name="telemetry_probe" if probe_attached else None,
        active_output_count=len(connected_outputs),
        node_element_names=node_element_names,
    )
