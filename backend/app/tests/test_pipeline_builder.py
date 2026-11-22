"""Unit tests for the GStreamer pipeline DAG compiler."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.models import ConnectorEdge, ConnectorNode, VirtualChannel
from app.pipeline_builder import compile_channel_pipeline


class TestPipelineBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.rec_dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_linear_pipeline_and_tee_fanout(self) -> None:
        ch = VirtualChannel(
            id="ch-test",
            name="Test Fanout",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="Test", params={"pattern": "smpte"}),
                ConnectorNode(id="tr1", type="text_overlay", label="Overlay", params={"text": "CH1", "show_timecode": True}),
                ConnectorNode(id="out1", type="file_record", label="Rec", params={"filename": "out.mp4", "container": "mp4"}),
                ConnectorNode(id="out2", type="web_preview", label="Preview", params={"width": 640, "fps": 10}),
            ],
            edges=[
                ConnectorEdge(id="e1", source="in1", target="tr1"),
                ConnectorEdge(id="e2", source="tr1", target="out1"),
                ConnectorEdge(id="e3", source="tr1", target="out2"),
            ],
        )
        compiled = compile_channel_pipeline(ch, self.rec_dir)
        self.assertTrue(compiled.is_valid, compiled.validation_errors)
        self.assertEqual(compiled.active_output_count, 2)
        self.assertEqual(compiled.preview_sink_names, ["preview_sink_out2"])
        self.assertIn("videotestsrc name=src_in1", compiled.pipeline_description)
        self.assertIn("tee name=tee_tr1", compiled.pipeline_description)
        self.assertIn("mp4mux", compiled.pipeline_description)
        self.assertIn("appsink name=preview_sink_out2", compiled.pipeline_description)

    def test_compositor_pip_pipeline(self) -> None:
        ch = VirtualChannel(
            id="ch-pip",
            name="PiP",
            nodes=[
                ConnectorNode(id="in_a", type="videotestsrc", label="Main", params={"pattern": "smpte"}),
                ConnectorNode(id="in_b", type="rtsp_ingest", label="Cam", params={"location": "rtsp://10.0.0.5/live"}),
                ConnectorNode(id="comp", type="compositor", label="PiP", params={"output_width": 1280, "output_height": 720}),
                ConnectorNode(id="out_srt", type="srt_output", label="SRT", params={"uri": "srt://127.0.0.1:9001"}),
            ],
            edges=[
                ConnectorEdge(id="e1", source="in_a", target="comp", target_handle="in_0"),
                ConnectorEdge(id="e2", source="in_b", target="comp", target_handle="in_1"),
                ConnectorEdge(id="e3", source="comp", target="out_srt", target_handle="in"),
            ],
        )
        compiled = compile_channel_pipeline(ch, self.rec_dir)
        self.assertTrue(compiled.is_valid, compiled.validation_errors)
        self.assertIn("comp_comp.sink_0", compiled.pipeline_description)
        self.assertIn("comp_comp.sink_1", compiled.pipeline_description)
        self.assertIn("compositor name=comp_comp", compiled.pipeline_description)
        self.assertIn("srtsink name=srt_out_srt", compiled.pipeline_description)

    def test_cycle_detection(self) -> None:
        ch = VirtualChannel(
            id="ch-cyc",
            name="Cyclic",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="In"),
                ConnectorNode(id="t1", type="video_scale", label="Scale 1"),
                ConnectorNode(id="t2", type="video_balance", label="Bal 2"),
                ConnectorNode(id="out1", type="web_preview", label="Preview"),
            ],
            edges=[
                ConnectorEdge(id="e1", source="in1", target="t1"),
                ConnectorEdge(id="e2", source="t1", target="t2"),
                ConnectorEdge(id="e3", source="t2", target="t1"),
                ConnectorEdge(id="e4", source="t2", target="out1"),
            ],
        )
        compiled = compile_channel_pipeline(ch, self.rec_dir)
        self.assertFalse(compiled.is_valid)
        self.assertTrue(any("Cycle detected" in e for e in compiled.validation_errors))

    def test_segmented_recording_uses_splitmuxsink(self) -> None:
        ch = VirtualChannel(
            id="ch-seg",
            name="Segmented",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="In"),
                ConnectorNode(
                    id="out1",
                    type="file_record",
                    label="SegRec",
                    params={"filename": "seg.mkv", "container": "mkv", "segment_seconds": 60},
                ),
            ],
            edges=[ConnectorEdge(id="e1", source="in1", target="out1")],
        )
        compiled = compile_channel_pipeline(ch, self.rec_dir)
        self.assertTrue(compiled.is_valid, compiled.validation_errors)
        self.assertIn("splitmuxsink", compiled.pipeline_description)
        self.assertIn("muxer=matroskamux", compiled.pipeline_description)

    def test_timecode_modes_and_clockoverlay(self) -> None:
        # Wall-clock mode -> clockoverlay with custom format and alignment
        ch_clock = VirtualChannel(
            id="ch-clk",
            name="Clock TC",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="In"),
                ConnectorNode(
                    id="txt1",
                    type="text_overlay",
                    label="Bug",
                    params={
                        "text": "STUDIO A & B",
                        "timecode_mode": "clock",
                        "timecode_prefix": "UTC ",
                        "timecode_format": "%H:%M:%S",
                        "timecode_valignment": "top",
                        "timecode_halignment": "right",
                    },
                ),
                ConnectorNode(id="out1", type="web_preview", label="Prev"),
            ],
            edges=[
                ConnectorEdge(id="e1", source="in1", target="txt1"),
                ConnectorEdge(id="e2", source="txt1", target="out1"),
            ],
        )
        compiled_clk = compile_channel_pipeline(ch_clock, self.rec_dir)
        self.assertTrue(compiled_clk.is_valid, compiled_clk.validation_errors)
        self.assertIn('text="STUDIO A &amp; B"', compiled_clk.pipeline_description)
        self.assertIn("clockoverlay name=clock_txt1", compiled_clk.pipeline_description)
        self.assertIn('time-format="%H:%M:%S"', compiled_clk.pipeline_description)
        self.assertIn('text="UTC "', compiled_clk.pipeline_description)
        self.assertIn("valignment=top halignment=right", compiled_clk.pipeline_description)
        self.assertIn("silent=false", compiled_clk.pipeline_description)

        # Off mode -> both timeoverlay and clockoverlay stay in pipeline with silent=true for live switching
        ch_clock.nodes[1].params["timecode_mode"] = "off"
        compiled_off = compile_channel_pipeline(ch_clock, self.rec_dir)
        self.assertTrue(compiled_off.is_valid)
        self.assertIn("timeoverlay name=time_txt1", compiled_off.pipeline_description)
        self.assertIn("clockoverlay name=clock_txt1", compiled_off.pipeline_description)
        self.assertEqual(compiled_off.pipeline_description.count("silent=true"), 2)

    def test_web_preview_preserves_feed_aspect_ratio(self) -> None:
        # 4:3 source -> 640x480 preview
        ch_43 = VirtualChannel(
            id="ch-43",
            name="4:3 Feed",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="4:3", params={"width": 800, "height": 600}),
                ConnectorNode(id="prev", type="web_preview", label="Preview", params={"width": 640, "fps": 10}),
            ],
            edges=[ConnectorEdge(id="e1", source="in1", target="prev")],
        )
        comp_43 = compile_channel_pipeline(ch_43, self.rec_dir)
        self.assertTrue(comp_43.is_valid)
        self.assertIn("width=640,height=480,pixel-aspect-ratio=1/1", comp_43.pipeline_description)

        # 16:9 source rotated 90 deg -> 9:16 vertical preview (640x1138)
        ch_vert = VirtualChannel(
            id="ch-vert",
            name="Vertical",
            nodes=[
                ConnectorNode(id="in1", type="videotestsrc", label="16:9", params={"width": 1280, "height": 720}),
                ConnectorNode(id="rot", type="video_balance", label="Rotate", params={"flip_method": "clockwise"}),
                ConnectorNode(id="prev", type="web_preview", label="Preview", params={"width": 640, "fps": 10}),
            ],
            edges=[
                ConnectorEdge(id="e1", source="in1", target="rot"),
                ConnectorEdge(id="e2", source="rot", target="prev"),
            ],
        )
        comp_vert = compile_channel_pipeline(ch_vert, self.rec_dir)
        self.assertTrue(comp_vert.is_valid)
        self.assertIn("width=640,height=1138,pixel-aspect-ratio=1/1", comp_vert.pipeline_description)

        # Dynamic RTSP without fixed scaler -> preserves native resolution/aspect ratio
        ch_rtsp = VirtualChannel(
            id="ch-rtsp",
            name="Dynamic RTSP",
            nodes=[
                ConnectorNode(id="in1", type="rtsp_ingest", label="Cam"),
                ConnectorNode(id="prev", type="web_preview", label="Preview", params={"width": 640, "fps": 10}),
            ],
            edges=[ConnectorEdge(id="e1", source="in1", target="prev")],
        )
        comp_rtsp = compile_channel_pipeline(ch_rtsp, self.rec_dir)
        self.assertTrue(comp_rtsp.is_valid)
        self.assertNotIn("videoscale", comp_rtsp.pipeline_description)


if __name__ == "__main__":
    unittest.main()
