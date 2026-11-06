from typing import Any, Optional

def compute_derived_status(
    live_at: Optional[str],
    region_matches: bool,
    modules_match: bool,
    admins_match: bool,
    sso_required: bool,
    sso_metadata_present: bool,
    has_open_tasks: bool,
) -> str:
    """
    Derived status computed on read.
    Rules in order:
    1. live_at is not null -> live
    2. Region, modules, and admins match, and sso_required is true, and sso_metadata_present is false -> waiting_on_customer
    3. Region, modules, and admins match, SSO does not block, and no task is open -> ready_for_review
    4. Otherwise -> provisioning
    """
    if live_at is not None:
        return "live"

    configuration_complete = region_matches and modules_match and admins_match

    if configuration_complete and sso_required and not sso_metadata_present:
        return "waiting_on_customer"

    sso_satisfied = (not sso_required) or sso_metadata_present

    if configuration_complete and sso_satisfied and not has_open_tasks:
        return "ready_for_review"

    return "provisioning"
