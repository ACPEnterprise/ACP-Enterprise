from logging.config import fileConfig

from alembic import context
from app.accounts_payable import models as accounts_payable_models  # noqa: F401
from app.beacon import models as beacon_models  # noqa: F401
from app.business_economics import models as business_economics_models  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.customer_migration import models as customer_migration_models  # noqa: F401
from app.customers import models as customer_models  # noqa: F401
from app.dispatch import models as dispatch_models  # noqa: F401
from app.engineering_capacity import models as engineering_capacity_models  # noqa: F401
from app.engineering_control import models as engineering_control_models  # noqa: F401
from app.engineering_control import (
    workstream_runtime as workstream_runtime_models,  # noqa: F401
)
from app.engineering_control.mobile import (
    control as workstream_control_models,  # noqa: F401
)
from app.engineering_control.mobile import (  # noqa: F401
    external_adoption as external_adoption_models,
)
from app.engineering_control.mobile import (
    notifications as mission_notification_models,  # noqa: F401
)
from app.engineering_control.repository_authorization import (
    models as repository_authorization_models,  # noqa: F401
)
from app.engineering_control.repository_operation import (
    models as repository_operation_models,  # noqa: F401
)
from app.engineering_control.review import (
    models as engineering_review_models,  # noqa: F401
)
from app.engineering_control.scheduler import models as scheduler_models  # noqa: F401
from app.engineering_execution import (
    models as engineering_execution_models,  # noqa: F401
)
from app.engineering_execution.composition import (
    models as composition_models,  # noqa: F401
)
from app.engineering_execution.controlled import (
    models as controlled_execution_models,  # noqa: F401
)
from app.engineering_execution.supervision import (
    models as supervision_models,  # noqa: F401
)
from app.estimates import models as estimate_models  # noqa: F401
from app.events import models as event_models  # noqa: F401
from app.execution_nodes import models as execution_node_models  # noqa: F401
from app.field_service import models as field_service_models  # noqa: F401
from app.financials import models as financial_models  # noqa: F401
from app.inventory import models as inventory_models  # noqa: F401
from app.invoicing import models as invoicing_models  # noqa: F401
from app.jobs import models as job_models  # noqa: F401
from app.luminary import models as luminary_models  # noqa: F401
from app.operational_migration import cutover_models  # noqa: F401
from app.operational_assets import models as operational_asset_models  # noqa: F401
from app.operational_migration import (
    models as operational_migration_models,  # noqa: F401
)
from app.payments import models as payment_models  # noqa: F401
from app.payroll import models as payroll_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.auth import models as auth_models  # noqa: F401
from app.platform.branch import models as branch_models  # noqa: F401
from app.platform.company import membership_models  # noqa: F401
from app.platform.company import models as company_models  # noqa: F401
from app.platform.employees import models as employee_models  # noqa: F401
from app.platform.idempotency import models as idempotency_models  # noqa: F401
from app.platform.notifications import models as notification_models  # noqa: F401
from app.platform.onboarding import models as onboarding_models  # noqa: F401
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users import identity_models  # noqa: F401
from app.platform.users import models as user_models  # noqa: F401
from app.price_book import models as price_book_models  # noqa: F401
from app.procurement_matching import models as procurement_matching_models  # noqa: F401
from app.purchasing import models as purchasing_models  # noqa: F401
from app.scheduling import models as scheduling_models  # noqa: F401
from app.service_agreements import models as service_agreement_models  # noqa: F401
from app.tax_policy import models as tax_policy_models  # noqa: F401
from app.timekeeping import models as timekeeping_models  # noqa: F401
from app.worker_control import models as worker_control_models  # noqa: F401
from app.worker_control.transport.persistence import (
    models as transport_models,  # noqa: F401
)
from app.worker_identity import models as worker_identity_models  # noqa: F401
from app.workforce import models as workforce_models  # noqa: F401
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("+asyncpg", "+psycopg"),
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
