"""Connector catalog API endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

from ..models import ConnectorDefinition
from ..registry import list_connector_definitions

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("", response_model=List[ConnectorDefinition])
def get_connectors() -> List[ConnectorDefinition]:
    """Return all registered Input, Transform, and Output connector definitions."""
    return list_connector_definitions()
