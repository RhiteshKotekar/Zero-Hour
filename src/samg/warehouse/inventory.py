"""Warehouse Inventory, SKU Registry and Rack Slot Mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SKUItem:
    sku: str
    name: str
    category: str
    weight_kg: float
    rack_id: str
    slot: str


# Preset inventory mapped to racks A01..A05 and B01..B05
DEFAULT_INVENTORY: dict[str, SKUItem] = {
    "SKU-101": SKUItem("SKU-101", "LiDAR Sensor Module", "Sensors", 0.8, "RACK-A01", "A01-1"),
    "SKU-102": SKUItem("SKU-102", "Optical Inspection Camera", "Vision", 1.2, "RACK-A01", "A01-2"),
    "SKU-103": SKUItem("SKU-103", "Precision Servo Actuator", "Motors", 2.5, "RACK-A02", "A02-1"),
    "SKU-104": SKUItem("SKU-104", "Motor Controller Board", "Electronics", 0.5, "RACK-A02", "A02-2"),
    "SKU-105": SKUItem("SKU-105", "High-Torque Drive Motor", "Motors", 5.0, "RACK-A03", "A03-1"),
    "SKU-106": SKUItem("SKU-106", "Heavy Gearbox Assembly", "Mechanical", 6.2, "RACK-A03", "A03-2"),
    "SKU-107": SKUItem("SKU-107", "AMR Battery Pack 48V", "Power", 7.5, "RACK-A04", "A04-1"),
    "SKU-108": SKUItem("SKU-108", "Battery Charging Interlock", "Power", 1.5, "RACK-A04", "A04-2"),
    "SKU-109": SKUItem("SKU-109", "RF Communication Transceiver", "Comms", 0.4, "RACK-A05", "A05-1"),
    "SKU-110": SKUItem("SKU-110", "Network Router Gateway", "Comms", 1.1, "RACK-A05", "A05-2"),
    "SKU-201": SKUItem("SKU-201", "Thermal Imaging Scanner", "Diagnostics", 1.6, "RACK-B01", "B01-1"),
    "SKU-202": SKUItem("SKU-202", "Vibration Diagnostic Kit", "Diagnostics", 2.0, "RACK-B01", "B01-2"),
    "SKU-203": SKUItem("SKU-203", "Structural Fastener Set", "Hardware", 3.0, "RACK-B02", "B02-1"),
    "SKU-204": SKUItem("SKU-204", "Hydraulic Coupling Flange", "Hardware", 4.5, "RACK-B02", "B02-2"),
    "SKU-205": SKUItem("SKU-205", "Reinforced Chassis Arm", "Structure", 8.0, "RACK-B03", "B03-1"),
    "SKU-206": SKUItem("SKU-206", "Polyurethane Drive Wheel", "Structure", 3.5, "RACK-B03", "B03-2"),
    "SKU-207": SKUItem("SKU-207", "Safety E-Stop Controller", "Safety", 0.9, "RACK-B04", "B04-1"),
    "SKU-208": SKUItem("SKU-208", "Protective Bump Sensor", "Safety", 1.4, "RACK-B04", "B04-2"),
    "SKU-209": SKUItem("SKU-209", "Automated Barcode Scanner", "Logistics", 0.7, "RACK-B05", "B05-1"),
    "SKU-210": SKUItem("SKU-210", "RFID Tag Encoder Unit", "Logistics", 1.8, "RACK-B05", "B05-2"),
}


class InventoryManager:
    """Manages warehouse stock items and rack slot locations."""

    def __init__(self, catalog: dict[str, SKUItem] | None = None) -> None:
        self.catalog = dict(catalog or DEFAULT_INVENTORY)

    def get_item(self, sku: str) -> SKUItem | None:
        return self.catalog.get(sku)

    def get_rack_for_sku(self, sku: str) -> str | None:
        item = self.catalog.get(sku)
        return item.rack_id if item else None

    def all_skus(self) -> list[str]:
        return sorted(self.catalog.keys())

