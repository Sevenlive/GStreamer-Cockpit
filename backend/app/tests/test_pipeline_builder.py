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


if __name__ == "__main__":
    unittest.main()
