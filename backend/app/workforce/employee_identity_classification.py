from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.users.models import User

SYNTHETIC_REQUEST_KEYS = frozenset(
    {
        "acp-employee-beta-v1",
        "preview.synthetic.tenant.v1",
    }
)


async def employee_is_synthetic(
    session: AsyncSession, *, employee: Employee
) -> bool:
    """Classify known acceptance fixtures from durable identity evidence."""
    number = employee.employee_number.strip().upper()
    if number.startswith(("SYN-", "SYN_", "SYNTHETIC", "BETA")):
        return True
    onboarding = await session.scalar(
        select(IdentityOnboardingRequest).where(
            IdentityOnboardingRequest.company_id == employee.company_id,
            IdentityOnboardingRequest.employee_id == employee.id,
        )
    )
    if onboarding is not None and onboarding.request_key in SYNTHETIC_REQUEST_KEYS:
        return True
    if employee.membership_id is None:
        return False
    login = await session.scalar(
        select(User.normalized_email)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.company_id == employee.company_id,
            Membership.id == employee.membership_id,
        )
    )
    return bool(login and login.endswith(".invalid"))
