"""Unit tests for EngineManager lifecycle, simulation preview frames, and persistence."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.engine.manager import EngineManager
from app.models import ChannelState


class TestEngineManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.rec_dir = Path(self.tmp.name) / "recordings"
        self.manager = EngineManager(
            data_dir=self.data_dir,
            recordings_dir=self.rec_dir,
            force_simulation=True,
        )

    def tearDown(self) -> None:
        self.manager.shutdown()
        self.tmp.cleanup()

    def test_seeded_channels_and_start_stop_preview(self) -> None:
        snaps = self.manager.list_snapshots()
        self.assertEqual(len(snaps), 3)

        ch_id = snaps[0].channel.id
        started = self.manager.start_channel(ch_id)
        self.assertEqual(started.telemetry.state, ChannelState.RUNNING)

        # Wait briefly for simulation runner to generate a JPEG preview frame
        frame = None
        for _ in range(20):
            frame = self.manager.get_preview_frame(ch_id)
            if frame:
                break
            time.sleep(0.05)

        self.assertIsNotNone(frame)
        assert frame is not None
        # Valid JPEG SOI header
        self.assertTrue(frame.startswith(b"\xff\xd8"))

        # Live update overlay text while running
        updated = self.manager.update_node_params(
            ch_id,
            "tr_overlay",
            {"text": "ON AIR • STUDIO A"},
        )
        overlay = next(n for n in updated.channel.nodes if n.id == "tr_overlay")
        self.assertEqual(overlay.params["text"], "ON AIR • STUDIO A")

        stopped = self.manager.stop_channel(ch_id)
        self.assertEqual(stopped.telemetry.state, ChannelState.STOPPED)

    def test_create_and_delete_channel_persists(self) -> None:
        created = self.manager.create_channel(
            name="CH-99 • Custom SRT",
            description="Test channel",
            preset="pip_switcher",
        )
        cid = created.channel.id
        self.assertEqual(len(created.channel.nodes), 5)

        # Reload manager from same data_dir to verify persistence
        reloaded = EngineManager(
            data_dir=self.data_dir,
            recordings_dir=self.rec_dir,
            force_simulation=True,
        )
        try:
            snap = reloaded.get_snapshot(cid)
            self.assertEqual(snap.channel.name, "CH-99 • Custom SRT")
        finally:
            reloaded.shutdown()

        self.manager.delete_channel(cid)
        with self.assertRaises(KeyError):
            self.manager.get_snapshot(cid)

    def test_hot_swap_transform_keeps_recording_running(self) -> None:
        from app.models import ConnectorEdge, ConnectorNode

        snap = self.manager.start_channel("ch-01")
        initial_run_id = snap.telemetry.run_id
        self.assertEqual(initial_run_id, 1)

        # Verify 2-stage intervideosink/intervideosrc compilation
        compiled = self.manager._compiled["ch-01"]
        self.assertIsNotNone(compiled.source_pipeline_description)
        self.assertIsNotNone(compiled.output_pipeline_description)
        self.assertIn("intervideosink", compiled.source_pipeline_description or "")
        self.assertIn("intervideosrc", compiled.output_pipeline_description or "")

        # Insert a new video_balance transform between tr_overlay and the two outputs while running
        nodes = list(snap.channel.nodes) + [
            ConnectorNode(id="tr_bal", type="video_balance", label="Color", params={"saturation": 0.2})
        ]
        edges = [
            ConnectorEdge(id="e1", source="in_test", target="tr_overlay"),
            ConnectorEdge(id="e_bal", source="tr_overlay", target="tr_bal"),
            ConnectorEdge(id="e2", source="tr_bal", target="out_preview"),
            ConnectorEdge(id="e3", source="tr_bal", target="out_rec"),
        ]
        updated = self.manager.update_channel_graph("ch-01", nodes, edges)
        # run_id MUST stay 1 (recording/outputs were NOT restarted!)
        self.assertEqual(updated.telemetry.run_id, initial_run_id)
        self.assertEqual(updated.telemetry.state, ChannelState.RUNNING)


if __name__ == "__main__":
    unittest.main()
