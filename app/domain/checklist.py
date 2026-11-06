from typing import Any, Optional

CATALOG_MODULES = ["projects", "time", "billing"]

def build_checklist(
    contract_region: str,
    tenant_region: Optional[str],
    contract_modules: list[str],
    tenant_modules: list[str],
    contract_admin_emails: list[str],
    tenant_admin_emails: list[str],
    sso_required: bool,
    sso_metadata_present: bool,
    live_at: Optional[str],
) -> dict[str, Any]:
    # Catalog order for modules
    expected_modules = [m for m in CATALOG_MODULES if m in set(contract_modules)]
    actual_modules = [m for m in CATALOG_MODULES if m in set(tenant_modules)]
    modules_ok = set(expected_modules) == set(actual_modules)

    # Sorted emails for admins
    expected_admins = sorted([e.lower() for e in contract_admin_emails])
    actual_admins = sorted([e.lower() for e in tenant_admin_emails])
    admins_ok = set(expected_admins) == set(actual_admins)

    region_ok = tenant_region == contract_region

    if not sso_required:
        sso_state = "not_applicable"
        sso_ok = True
    elif sso_metadata_present:
        sso_state = "ready"
        sso_ok = True
    else:
        sso_state = "blocking"
        sso_ok = False

    return {
        "region": {
            "expected": contract_region,
            "actual": tenant_region,
            "ok": region_ok,
        },
        "modules": {
            "expected": expected_modules,
            "actual": actual_modules,
            "ok": modules_ok,
        },
        "admins": {
            "expected": expected_admins,
            "actual": actual_admins,
            "ok": admins_ok,
        },
        "sso": {
            "state": sso_state,
            "ok": sso_ok,
        },
        "live": {
            "ok": bool(live_at),
        },
    }
