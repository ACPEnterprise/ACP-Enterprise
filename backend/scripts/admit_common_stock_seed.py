#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from app.database.session import AsyncSessionFactory
from app.inventory.common_stock_seed import (
    common_stock_admission_service,
    read_common_stock_workbook,
)


async def run() -> int:
    parser = argparse.ArgumentParser(description="Inspect or admit the owner common-stock workbook")
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--admit", action="store_true")
    parser.add_argument("--company-id", type=UUID)
    parser.add_argument("--actor-user-id", type=UUID)
    args = parser.parse_args()
    workbook = read_common_stock_workbook(args.workbook)
    result: dict[str, object] = {
        "source_filename": workbook.source_path.name,
        "source_digest": workbook.source_digest,
        "source_rows_read": len(workbook.rows),
        "acp_materials_proposed": workbook.proposed_count,
        "rows_held": workbook.held_count,
        "held_rows": [
            {"source_row_number": row.source_row_number, "reason": row.hold_reason}
            for row in workbook.rows
            if row.disposition == "held"
        ],
        "mode": "dry_run",
    }
    if args.admit:
        if args.company_id is None or args.actor_user_id is None:
            parser.error("--admit requires --company-id and --actor-user-id")
        async with AsyncSessionFactory() as session:
            admitted, held = await common_stock_admission_service.admit(
                session,
                workbook=workbook,
                company_id=args.company_id,
                actor_user_id=args.actor_user_id,
            )
        result.update({"mode": "admitted", "records_admitted": admitted, "records_held": held})
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
