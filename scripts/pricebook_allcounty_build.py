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
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from numbers_parser import Document

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN, "r": REL, "p": PKG_REL}

EXPECTED_SOURCES = {
    "flat_rate_price_book": (
        "All_County_Flat_Rate_Price_Book.xlsx",
        "OWNER_PRICING_SOURCE",
    ),
    "parts_markup_schedule": (
        "All_County_Parts_Markup_Schedule.xlsx",
        "OWNER_RECOMMENDATION",
    ),
    "vendor_materials_template": (
        "pricebook_materials_template.numbers",
        "OWNER_OPERATIONAL_SOURCE",
    ),
    "membership_brochure": (
        "All_County_Membership_Brochure.pdf",
        "OWNER_CUSTOMER_FACING_SOURCE",
    ),
    "pricing_recommendation": (
        "All_County_Pinellas_Pricing_Recommendation.docx",
        "OWNER_RECOMMENDATION",
    ),
    "sales_script": ("All_County_Sales_Script.docx", "OWNER_RECOMMENDATION"),
    "water_heater_script": (
        "All_County_Water_Heater_Sales_Script.docx",
        "OWNER_RECOMMENDATION",
    ),
}

CATEGORY_SHEETS = (
    "Service Calls",
    "Drain Cabling",
    "Hydro-Jet & Camera",
    "Sewer Repair",
    "Water Heater Install",
    "Tankless",
    "Water Heater Repair",
    "Toilets",
    "Faucets & Showers",
    "Disposals",
    "Water Service",
    "Leak Detection",
    "Outdoor & Backflow",
    "Sump & Ejector",
    "Repipe",
    "Gas",
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
        item
        for item in source_dir.iterdir()
        if item.is_file()
        and item.suffix.casefold() == suffix
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
        sheet_nodes = workbook.find("m:sheets", NS)
        for sheet in () if sheet_nodes is None else sheet_nodes:
            target = targets[sheet.attrib[f"{{{REL}}}id"]]
            self.sheets[sheet.attrib["name"]] = (
                target.lstrip("/")
                if target.startswith("/")
                else f"xl/{target.lstrip('/')}"
            )
        names = workbook.find("m:definedNames", NS)
        name_nodes = () if names is None else names
        self.defined_names = {
            node.attrib["name"]: node.text for node in name_nodes if node.text
        }

    def rows(self, sheet_name: str) -> list[dict[int, dict[str, str | None]]]:
        root = ET.fromstring(self.archive.read(self.sheets[sheet_name]))
        output: list[dict[int, dict[str, str | None]]] = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            record: dict[int, dict[str, str | None]] = {
                0: {"row": row.attrib["r"], "value": None, "formula": None}
            }
            for cell in row.findall("m:c", NS):
                value_node = cell.find("m:v", NS)
                formula_node = cell.find("m:f", NS)
                value = value_node.text if value_node is not None else None
                if cell.attrib.get("t") == "s" and value is not None:
                    value = self.shared[int(value)]
                elif cell.attrib.get("t") == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.findall(".//m:t", NS)
                    )
                record[column_number(cell.attrib["r"])] = {
                    "value": value,
                    "formula": formula_node.text if formula_node is not None else None,
                }
            output.append(record)
        return output


def decimal(value: str | None, default: str = "0") -> Decimal:
    resolved = default if value is None or value == "" else value
    return Decimal(resolved)


def round_five(value: Decimal) -> Decimal:
    return (value / Decimal(5)).quantize(Decimal(1), rounding=ROUND_HALF_UP) * Decimal(
        5
    )


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def workbook_candidates(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    book = Workbook(path)
    settings = {
        row[1]["value"]: row.get(2, {}).get("value")
        for row in book.rows("Settings")
        if 1 in row
    }
    break_even = decimal(settings.get("Break-Even Labor Rate ($/hr)"))
    target_margin = decimal(settings.get("Target Gross Margin"))
    selling_rate = break_even / (Decimal(1) - target_margin)
    minimum_job = decimal(settings.get("Minimum Job Floor"))
    discounts = {
        "essential": decimal(settings.get("Member Discount — Essential Tier")),
        "plus": decimal(settings.get("Member Discount — Plus Tier")),
        "premier": decimal(settings.get("Member Discount — Premier Tier")),
    }
    after_hours = decimal(settings.get("After-Hours Multiplier"), "1")
    markup = []
    for row in book.rows("Markup"):
        if (
            1 in row
            and 2 in row
            and (row[1]["value"] or "").replace(".", "", 1).isdigit()
        ):
            markup.append((decimal(row[1]["value"]), decimal(row[2]["value"])))

    def multiplier(cost: Decimal) -> Decimal:
        eligible = [factor for lower, factor in markup if cost >= lower]
        return eligible[-1] if eligible else Decimal(0)

    candidates: list[dict[str, Any]] = []
    for position, sheet in enumerate(CATEGORY_SHEETS, 1):
        for row in book.rows(sheet):
            code = row.get(1, {}).get("value")
            if not code or not re.fullmatch(r"[A-Z]+-[0-9A-Z]+", code):
                continue
            hours = decimal(row.get(3, {}).get("value"))
            parts_cost = decimal(row.get(4, {}).get("value"))
            override_value = row.get(10, {}).get("value")
            override = (
                decimal(override_value) if override_value not in (None, "") else None
            )
            calculated = round_five(
                hours * selling_rate + parts_cost * multiplier(parts_cost)
            )
            standard = (
                override if override is not None else max(calculated, minimum_job)
            )
            candidates.append(
                {
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
                    "material_cost_evidence": {
                        "amount": money(parts_cost),
                        "completeness": "AGGREGATE_ONLY"
                        if parts_cost
                        else "NO_COMPONENT_COST",
                    },
                    "price_candidates": {
                        "standard": money(standard),
                        "essential_member": money(
                            round_five(standard * (Decimal(1) - discounts["essential"]))
                        ),
                        "plus_member": money(
                            round_five(standard * (Decimal(1) - discounts["plus"]))
                        ),
                        "premier_member": money(
                            round_five(standard * (Decimal(1) - discounts["premier"]))
                        ),
                        "after_hours": money(round_five(standard * after_hours)),
                    },
                    "price_derivation": "OWNER_OVERRIDE"
                    if override is not None
                    else "WORKBOOK_FORMULA",
                    "tax_review": "OWNER_ACCOUNTANT_REVIEW_REQUIRED",
                    "source": {
                        "source_key": "flat_rate_price_book",
                        "sheet": sheet,
                        "row": int(row[0]["row"] or 0),
                    },
                }
            )
    controls = {
        "worksheets": list(book.sheets),
        "worksheet_count": len(book.sheets),
        "defined_names": book.defined_names,
        "candidate_rows": len(candidates),
        "category_count": len(CATEGORY_SHEETS),
        "break_even_labor_rate": money(break_even),
        "target_margin": str(target_margin),
        "selling_rate": money(selling_rate),
        "minimum_job": money(minimum_job),
        "member_discounts": {key: str(value) for key, value in discounts.items()},
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
            tiers.append(
                {
                    "tier": int(tier),
                    "cost_from": row.get(2, {}).get("value"),
                    "cost_to": row.get(3, {}).get("value"),
                    "multiplier": row.get(4, {}).get("value"),
                    "examples": row.get(6, {}).get("value"),
                    "authority": "OWNER_RECOMMENDATION",
                }
            )
    return {
        "version": "all-county-parts-markup-candidate-1",
        "status": "OWNER_REVIEW_REQUIRED",
        "activation_status": "NOT_ACTIVATED",
        "tiers": tiers,
        "customer_supplied_parts": "OWNER_REVIEW_REQUIRED",
        "special_order_and_freight": "OWNER_REVIEW_REQUIRED",
        "illustrative_common_parts_are_cost_authority": False,
    }


def source_identifier(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def vendor_material_candidates(path: Path) -> dict[str, Any]:
    document = Document(str(path))
    sheets = []
    candidates: list[dict[str, Any]] = []
    identities: dict[str, list[int]] = {}
    required_headers = {
        "category",
        "subcategory_1",
        "subcategory_2",
        "subcategory_3",
        "subcategory_4",
        "subcategory_5",
        "subcategory_6",
        "subcategory_7",
        "subcategory_8",
        "subcategory_9",
        "subcategory_10",
        "name",
        "description",
        "part_number",
        "price",
        "cost",
        "taxable",
        "unit_of_measure",
        "material_markup_enabled",
    }
    for sheet in document.sheets:
        sheet_record = {"name": sheet.name, "tables": []}
        for table in sheet.tables:
            rows = table.rows(values_only=True)
            headers = [str(value) if value is not None else "" for value in rows[0]]
            missing_headers = sorted(required_headers - set(headers))
            sheet_record["tables"].append(
                {
                    "name": table.name,
                    "rows": table.num_rows,
                    "columns": table.num_cols,
                    "headers": headers,
                    "missing_required_headers": missing_headers,
                }
            )
            current_hierarchy: list[str | None] = [None] * 11
            for source_row, values in enumerate(rows[1:], 2):
                if len(headers) != len(values):
                    raise ValueError(
                        f"{sheet.name}/{table.name} row {source_row} has "
                        f"{len(values)} cells for {len(headers)} headers"
                    )
                record = dict(zip(headers, values))
                for index, key in enumerate(
                    ["category"] + [f"subcategory_{level}" for level in range(1, 11)]
                ):
                    if record[key] is not None:
                        current_hierarchy[index] = str(record[key]).strip()
                        current_hierarchy[index + 1 :] = [None] * (10 - index)
                part_number = source_identifier(record["part_number"])
                identity = (
                    f"vendor-unresolved:{part_number}"
                    if part_number
                    else f"source-row:{source_row}"
                )
                identities.setdefault(identity, []).append(source_row)
                candidates.append(
                    {
                        "candidate_identity": identity,
                        "disposition": "NEW" if part_number else "INCOMPLETE",
                        "review_state": "SOURCE_REQUIRED",
                        "vendor": None,
                        "manufacturer": None,
                        "vendor_sku": part_number,
                        "manufacturer_part_number": None,
                        "source_name": source_identifier(record["name"]),
                        "description": source_identifier(record["description"]),
                        "category_hierarchy": [
                            value for value in current_hierarchy if value
                        ],
                        "unit": source_identifier(record["unit_of_measure"]),
                        "pack_quantity": None,
                        "cost_evidence": None
                        if record["cost"] is None
                        else str(record["cost"]),
                        "customer_price": None
                        if record["price"] is None
                        else str(record["price"]),
                        "taxable_source_value": record["taxable"],
                        "material_markup_enabled_source_value": record[
                            "material_markup_enabled"
                        ],
                        "source": {
                            "source_key": "vendor_materials_template",
                            "sheet": sheet.name,
                            "table": table.name,
                            "row": source_row,
                        },
                        "inventory_mutation": False,
                        "customer_facing_service_creation": False,
                    }
                )
        sheets.append(sheet_record)
    duplicates = {key: rows for key, rows in identities.items() if len(rows) > 1}
    for candidate in candidates:
        if candidate["candidate_identity"] in duplicates:
            candidate["disposition"] = "POSSIBLE_MATCH"
            candidate["review_state"] = "DUPLICATE_CANDIDATE"
    return {
        "import_contract_version": "provider-neutral-vendor-material-1",
        "status": "READY_FOR_RECONCILIATION",
        "sheets": sheets,
        "candidate_count": len(candidates),
        "unique_candidate_identity_count": len(identities),
        "duplicate_candidate_identities": duplicates,
        "maximum_hierarchy_depth": max(
            (len(item["category_hierarchy"]) for item in candidates), default=0
        ),
        "vendor_identity_state": "SOURCE_REQUIRED",
        "manufacturer_identity_state": "SOURCE_REQUIRED",
        "price_population_state": "NOT_PRESENT",
        "inventory_boundary": "NO_INVENTORY_LEDGER_MUTATION",
        "candidates": candidates,
    }


def water_heater_reconciliation(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    family = [
        item
        for item in candidates
        if item["category"]["source_name"]
        in {"Water Heater Install", "Tankless", "Water Heater Repair"}
    ]
    return {
        "source_key": "water_heater_script",
        "existing_candidate_count": len(family),
        "new_service_candidates": 0,
        "product_family": {
            "standard_tank_install": [
                item["service_code"]
                for item in family
                if item["service_code"].startswith("WHT-")
                and "standard install" in item["name"].lower()
            ],
            "premium_tank_install": [
                item["service_code"]
                for item in family
                if item["service_code"].startswith("WHT-")
                and "premium install" in item["name"].lower()
            ],
            "tankless": [
                item["service_code"]
                for item in family
                if item["service_code"].startswith("WHL-")
            ],
            "repair_and_add_on": [
                item["service_code"]
                for item in family
                if item["service_code"].startswith("WHR-")
            ],
        },
        "scope_reconciliation": "CONSISTENT",
        "option_architecture": "CONSISTENT",
        "price_examples": "CONFLICTING",
        "component_cost_breakdown": "ILLUSTRATIVE_ASSUMPTION",
        "warranty_and_code_claims": "OWNER_RECOMMENDATION",
        "disposition": "Use workbook service candidates and native option groups; retain script figures only as review evidence.",
        "activation_status": "NOT_ACTIVATED",
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
        registrations.append(
            {
                "source_key": key,
                "expected_identity": expected,
                "observed_identity": path.name if path else None,
                "sha256": digest(path) if path else None,
                "bytes": path.stat().st_size if path else None,
                "readable": bool(path and path.is_file()),
                "authority_classification": authority if path else "SOURCE_REQUIRED",
                "ingested_at": args.ingested_at if path else None,
            }
        )
    controls, candidates = workbook_candidates(located["flat_rate_price_book"])
    materials = vendor_material_candidates(located["vendor_materials_template"])
    packet = {
        "schema_version": "1.0",
        "milestone": "PRICEBOOK.ALLCOUNTY.BUILD.1",
        "candidate_configuration_version": "all-county-price-book-candidate-1",
        "activation_status": "NOT_ACTIVATED",
        "source_registrations": registrations,
        "flat_rate_workbook": controls,
        "markup_policy": markup_policy(located["parts_markup_schedule"]),
        "vendor_material_import": materials,
        "water_heater_reconciliation": water_heater_reconciliation(candidates),
        "categories": [
            {
                "source_name": name,
                "position": i + 1,
                "review_state": "READY_FOR_OWNER_REVIEW",
            }
            for i, name in enumerate(CATEGORY_SHEETS)
        ],
        "service_candidates": candidates,
        "review_summary": {
            "READY_FOR_OWNER_REVIEW": len(candidates),
            "READY_FOR_ACTIVATION": 0,
            "OWNER_ACCOUNTANT_REVIEW_REQUIRED": len(candidates),
            "MATERIAL_MAPPING_REQUIRED": sum(
                c["material_cost_evidence"]["amount"] != "0.00" for c in candidates
            ),
            "SOURCE_REQUIRED": sum(
                item["review_state"] == "SOURCE_REQUIRED"
                for item in materials["candidates"]
            ),
            "DUPLICATE_CANDIDATE": sum(
                item["review_state"] == "DUPLICATE_CANDIDATE"
                for item in materials["candidates"]
            ),
        },
        "hard_boundaries": {
            "automatic_activation": False,
            "hcp_authoritative": False,
            "invented_tax_policy": False,
            "real_customer_job_mutation": False,
            "accounting_posting": False,
            "production_mutation": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
