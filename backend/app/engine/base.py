"""Abstract base class for Virtual Channel pipeline runners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Any, Callable, Deque, List, Optional

from ..models import ChannelState, ChannelTelemetry, LogEntry, LogLevel, VirtualChannel
from ..pipeline_builder import CompiledPipeline


class ChannelRunner(ABC):
    """Lifecycle and telemetry interface for a single virtual channel."""

    def __init__(
        self,
        channel: VirtualChannel,
        compiled: CompiledPipeline,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.channel = channel
        self.compiled = compiled
        self._on_event = on_event
        self._logs: Deque[LogEntry] = deque(maxlen=200)
        self._state: ChannelState = ChannelState.STOPPED
        self._error_message: Optional[str] = None

    def _log(self, level: LogLevel, source: str, message: str) -> None:
        self._logs.append(LogEntry(level=level, source=source, message=message))
        if self._on_event:
            try:
                self._on_event(self.channel.id, "log")
            except Exception:
                pass

    def get_logs(self, limit: int = 80) -> List[LogEntry]:
        items = list(self._logs)
        return items[-limit:]

    @abstractmethod
    def start(self) -> None:
        """Start the channel pipeline."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the channel pipeline cleanly."""

    @abstractmethod
    def get_telemetry(self) -> ChannelTelemetry:
        """Return current telemetry snapshot."""

    @abstractmethod
    def get_latest_frame(self) -> Optional[bytes]:
        """Return latest JPEG frame bytes for live preview, if available."""

    def update_live_param(self, node_id: str, param_name: str, value: Any) -> bool:
        """Attempt to update a parameter on a running pipeline without restart."""
        return False
