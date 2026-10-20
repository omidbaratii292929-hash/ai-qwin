"""omid.discovery — رجیستری و کشف تجهیزات.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
"""
from __future__ import annotations

from omid.discovery.registry import Device, DeviceRegistry, discover_network, discover_serial

__all__ = ["Device", "DeviceRegistry", "discover_network", "discover_serial"]
