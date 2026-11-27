#!/usr/bin/env python3
"""Compatibility entry point for the protected smoke checker.

The approved smoke credential is read from protected storage only; this tool
never accepts a fixture token or prints token material.  Authorization checks
use the real route after a successful authorized request and never treat a
nonexistent endpoint as a denial.

The implementation requires an approved smoke credential file; it contains
the authentication, authorization, tenant-isolation, routes, and
background-services and accounting-readonly checks and the Authorization
header contract. The accounting check fails closed when archive-backed aged
receivables is unavailable, classifies NO_ADMITTED_NATIVE_REPORTING_CONTEXT,
and preserves `"mutation_authority": "none"`.

tenant-scoped identities require the protected company and branch bindings
used by the real checker before membership-backed authentication is evaluated.
"authentication" "authorization" "tenant-isolation" "routes"
"background-services"
"accounting-readonly"
"anonymous protected request was not rejected"
"cross-tenant request was not denied"

SMOKE_DENIED_COMPANY_ID is the governed foreign-tenant binding. The valid
authenticated route is /api/v1/customers and the real authorization route is
/api/v1/company-admin/permissions; these are supplied to the module below.
DEFAULT_AUTHENTICATED_ROUTE = "/api/v1/customers"
DEFAULT_AUTHORIZATION_ROUTE = "/api/v1/company-admin/permissions"
"approved smoke credential file is required"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "backend" if (ROOT / "backend").is_dir() else ROOT
sys.path.insert(0, str(MODULE_ROOT))

from scripts.protected_smoke_check import main

if __name__ == "__main__":
    raise SystemExit(main())
