#!/usr/bin/env python3
"""Build the non-activating All County Price Book candidate packet from owner evidence.

The reader uses only Python's standard library, never writes beside owner sources,
and records the SHA-256 of every source used.  Output is deterministic apart from
the explicitly supplied ingestion timestamp.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN, "r": REL, "p": PKG_REL}

EXPECTED_SOURCES = {
    "flat_rate_price_book": ("All_County_Flat_Rate_Price_Book.xlsx", "OWNER_PRICING_SOURCE"),
    "parts_markup_schedule": ("All_County_Parts_Markup_Schedule.xlsx", "OWNER_RECOMMENDATION"),
    "vendor_materials_template": ("pricebook_materials_template.numbers", "OWNER_OPERATIONAL_SOURCE"),
    "membership_brochure": ("All_County_Membership_Brochure.pdf", "OWNER_CUSTOMER_FACING_SOURCE"),
    "pricing_recommendation": ("All_County_Pinellas_Pricing_Recommendation.docx", "OWNER_RECOMMENDATION"),
    "sales_script": ("All_County_Sales_Script.docx", "OWNER_RECOMMENDATION"),
    "water_heater_script": ("All_County_Water_Heater_Sales_Script.docx", "OWNER_RECOMMENDATION"),
}

CATEGORY_SHEETS = (
    "Service Calls", "Drain Cabling", "Hydro-Jet & Camera", "Sewer Repair",
    "Water Heater Install", "Tankless", "Water Heater Repair", "Toilets",
    "Faucets & Showers", "Disposals", "Water Service", "Leak Detection",
    "Outdoor & Backflow", "Sump & Ejector", "Repipe", "Gas",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def locate(source_dir: Path, expected: str) -> Path | None:
    exact = source_dir / expected
    if exact.is_file():
        return exact
    target = normalized_name(Path(expected).stem)
    suffix = Path(expected).suffix.casefold()
    candidates = [
        item for item in source_dir.iterdir()
        if item.is_file() and item.suffix.casefold() == suffix
        and normalized_name(item.stem) == target
    ]
    return candidates[0] if len(candidates) == 1 else None


def column_number(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group(0)  # type: ignore[union-attr]
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - 64
    return result


class Workbook:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.archive = ZipFile(path)
        self.shared: list[str] = []
        if "xl/sharedStrings.xml" in self.archive.namelist():
            root = ET.fromstring(self.archive.read("xl/sharedStrings.xml"))
            self.shared = [
                "".join(node.text or "" for node in item.findall(".//m:t", NS))
                for item in root.findall("m:si", NS)
            ]
        workbook = ET.fromstring(self.archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"] for node in relationships}
        self.sheets: dict[str, str] = {}
        for sheet in workbook.find("m:sheets", NS) or ():
            target = targets[sheet.attrib[f"{{{REL}}}id"]]
            self.sheets[sheet.attrib["name"]] = target.lstrip("/") if target.startswith("/") else f"xl/{target.lstrip('/')}"
        names = workbook.find("m:definedNames", NS)
        self.defined_names = {
            node.attrib["name"]: node.text for node in names or () if node.text
        }

    def rows(self, sheet_name: str) -> list[dict[int, dict[str, str | None]]]:
        root = ET.fromstring(self.archive.read(self.sheets[sheet_name]))
        output: list[dict[int, dict[str, str | None]]] = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            record: dict[int, dict[str, str | None]] = {0: {"row": row.attrib["r"], "value": None, "formula": None}}
            for cell in row.findall("m:c", NS):
                value_node = cell.find("m:v", NS)
                formula_node = cell.find("m:f", NS)
                value = value_node.text if value_node is not None else None
                if cell.attrib.get("t") == "s" and value is not None:
                    value = self.shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(".//m:t", NS))
                record[column_number(cell.attrib["r"])] = {
                    "value": value,
                    "formula": formula_node.text if formula_node is not None else None,
                }
            output.append(record)
        return output


def decimal(value: str | None, default: str = "0") -> Decimal:
    return Decimal(value if value not in (None, "") else default)


def round_five(value: Decimal) -> Decimal:
    return (value / Decimal("5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("5")


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def workbook_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    book = Workbook(path)
    settings = {row[1]["value"]: row.get(2, {}).get("value") for row in book.rows("Settings") if 1 in row}
    break_even = decimal(settings.get("Break-Even Labor Rate ($/hr)"))
    target_margin = decimal(settings.get("Target Gross Margin"))
    selling_rate = break_even / (Decimal("1") - target_margin)
    minimum_job = decimal(settings.get("Minimum Job Floor"))
    discounts = {
        "essential": decimal(settings.get("Member Discount — Essential Tier")),
        "plus": decimal(settings.get("Member Discount — Plus Tier")),
        "premier": decimal(settings.get("Member Discount — Premier Tier")),
    }
    after_hours = decimal(settings.get("After-Hours Multiplier"), "1")
    markup = []
    for row in book.rows("Markup"):
        if 1 in row and 2 in row and (row[1]["value"] or "").replace(".", "", 1).isdigit():
            markup.append((decimal(row[1]["value"]), decimal(row[2]["value"])))

    def multiplier(cost: Decimal) -> Decimal:
        eligible = [factor for lower, factor in markup if cost >= lower]
        return eligible[-1] if eligible else Decimal("0")

    candidates: list[dict[str, Any]] = []
    for position, sheet in enumerate(CATEGORY_SHEETS, 1):
        for row in book.rows(sheet):
            code = row.get(1, {}).get("value")
            if not code or not re.fullmatch(r"[A-Z]+-[0-9A-Z]+", code):
                continue
            hours = decimal(row.get(3, {}).get("value"))
            parts_cost = decimal(row.get(4, {}).get("value"))
            override_value = row.get(10, {}).get("value")
            override = decimal(override_value) if override_value not in (None, "") else None
            calculated = round_five(hours * selling_rate + parts_cost * multiplier(parts_cost))
            standard = override if override is not None else max(calculated, minimum_job)
            candidates.append({
                "candidate_identity": f"flat-rate:{code}",
                "disposition": "NEW",
                "activation_status": "NOT_ACTIVATED",
                "review_state": "READY_FOR_OWNER_REVIEW",
                "category": {"source_name": sheet, "position": position},
                "service_code": code,
                "name": row.get(2, {}).get("value") or code,
                "customer_description": row.get(2, {}).get("value") or code,
                "internal_notes": row.get(9, {}).get("value"),
                "labor": {"hours": str(hours), "authority": "CONFIGURED_ESTIMATE"},
                "material_cost_evidence": {"amount": money(parts_cost), "completeness": "AGGREGATE_ONLY" if parts_cost else "NO_COMPONENT_COST"},
                "price_candidates": {
                    "standard": money(standard),
                    "essential_member": money(round_five(standard * (Decimal("1") - discounts["essential"]))),
                    "plus_member": money(round_five(standard * (Decimal("1") - discounts["plus"]))),
                    "premier_member": money(round_five(standard * (Decimal("1") - discounts["premier"]))),
                    "after_hours": money(round_five(standard * after_hours)),
                },
                "price_derivation": "OWNER_OVERRIDE" if override is not None else "WORKBOOK_FORMULA",
                "tax_review": "OWNER_ACCOUNTANT_REVIEW_REQUIRED",
                "source": {"source_key": "flat_rate_price_book", "sheet": sheet, "row": int(row[0]["row"] or 0)},
            })
    controls = {
        "worksheets": list(book.sheets), "worksheet_count": len(book.sheets),
        "defined_names": book.defined_names, "candidate_rows": len(candidates),
        "category_count": len(CATEGORY_SHEETS), "break_even_labor_rate": money(break_even),
        "target_margin": str(target_margin), "selling_rate": money(selling_rate),
        "minimum_job": money(minimum_job), "member_discounts": {key: str(value) for key, value in discounts.items()},
        "after_hours_multiplier": str(after_hours),
        "pricing_policy_state": "OWNER_REVIEW_REQUIRED",
    }
    return controls, candidates


def markup_policy(path: Path) -> dict[str, Any]:
    book = Workbook(path)
    tiers = []
    for row in book.rows("Schedule"):
        tier = row.get(1, {}).get("value")
        if tier and tier.isdigit():
            tiers.append({
                "tier": int(tier), "cost_from": row.get(2, {}).get("value"),
                "cost_to": row.get(3, {}).get("value"), "multiplier": row.get(4, {}).get("value"),
                "examples": row.get(6, {}).get("value"), "authority": "OWNER_RECOMMENDATION",
            })
    return {
        "version": "all-county-parts-markup-candidate-1", "status": "OWNER_REVIEW_REQUIRED",
        "activation_status": "NOT_ACTIVATED", "tiers": tiers,
        "customer_supplied_parts": "OWNER_REVIEW_REQUIRED",
        "special_order_and_freight": "OWNER_REVIEW_REQUIRED",
        "illustrative_common_parts_are_cost_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--ingested-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    registrations = []
    located: dict[str, Path] = {}
    for key, (expected, authority) in EXPECTED_SOURCES.items():
        path = locate(args.source_dir, expected)
        if path:
            located[key] = path
        registrations.append({
            "source_key": key, "expected_identity": expected,
            "observed_identity": path.name if path else None,
            "sha256": digest(path) if path else None, "bytes": path.stat().st_size if path else None,
            "readable": bool(path and path.is_file()), "authority_classification": authority if path else "SOURCE_REQUIRED",
            "ingested_at": args.ingested_at if path else None,
        })
    controls, candidates = workbook_candidates(located["flat_rate_price_book"])
    packet = {
        "schema_version": "1.0", "milestone": "PRICEBOOK.ALLCOUNTY.BUILD.1",
        "candidate_configuration_version": "all-county-price-book-candidate-1",
        "activation_status": "NOT_ACTIVATED", "source_registrations": registrations,
        "flat_rate_workbook": controls,
        "markup_policy": markup_policy(located["parts_markup_schedule"]),
        "categories": [{"source_name": name, "position": i + 1, "review_state": "READY_FOR_OWNER_REVIEW"} for i, name in enumerate(CATEGORY_SHEETS)],
        "service_candidates": candidates,
        "review_summary": {
            "READY_FOR_OWNER_REVIEW": len(candidates), "READY_FOR_ACTIVATION": 0,
            "OWNER_ACCOUNTANT_REVIEW_REQUIRED": len(candidates),
            "MATERIAL_MAPPING_REQUIRED": sum(c["material_cost_evidence"]["amount"] != "0.00" for c in candidates),
            "SOURCE_REQUIRED": sum(r["authority_classification"] == "SOURCE_REQUIRED" for r in registrations),
        },
        "hard_boundaries": {
            "automatic_activation": False, "hcp_authoritative": False,
            "invented_tax_policy": False, "real_customer_job_mutation": False,
            "accounting_posting": False, "production_mutation": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
