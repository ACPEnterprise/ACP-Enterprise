class AdministrationPermission:
    MEMBERSHIP_READ = "COMPANY_MEMBERSHIP_READ"
    MEMBERSHIP_MANAGE = "COMPANY_MEMBERSHIP_MANAGE"
    BRANCH_ACCESS_MANAGE = "COMPANY_BRANCH_ACCESS_MANAGE"
    ROLE_READ = "COMPANY_ROLE_READ"
    ROLE_MANAGE = "COMPANY_ROLE_MANAGE"
    PERMISSION_MANAGE = "COMPANY_PERMISSION_MANAGE"
    COMPANY_ADMINISTER = "COMPANY_ADMINISTER"

    ALL = frozenset(
        {
            MEMBERSHIP_READ,
            MEMBERSHIP_MANAGE,
            BRANCH_ACCESS_MANAGE,
            ROLE_READ,
            ROLE_MANAGE,
            PERMISSION_MANAGE,
            COMPANY_ADMINISTER,
        }
    )


class CustomerPermission:
    READ = "COMPANY_CUSTOMER_READ"
    MANAGE = "COMPANY_CUSTOMER_MANAGE"

    ALL = frozenset({READ, MANAGE})


class LaunchPlatformPermission:
    AUDIT_READ = "COMPANY_AUDIT_READ"

    ALL = frozenset({AUDIT_READ})


class AnalyticsPermission:
    READ = "COMPANY_ANALYTICS_READ"

    ALL = frozenset({READ})


class BeaconPermission:
    REVIEW = "COMPANY_BEACON_REVIEW"

    ALL = frozenset({REVIEW})


class SchedulingPermission:
    READ = "COMPANY_SCHEDULING_READ"
    MANAGE = "COMPANY_SCHEDULING_MANAGE"

    ALL = frozenset({READ, MANAGE})


class JobPermission:
    READ = "COMPANY_JOB_READ"
    MANAGE = "COMPANY_JOB_MANAGE"
    EXECUTE = "COMPANY_JOB_EXECUTE"

    ALL = frozenset({READ, MANAGE, EXECUTE})


class DispatchPermission:
    READ = "COMPANY_DISPATCH_READ"
    MANAGE = "COMPANY_DISPATCH_MANAGE"

    ALL = frozenset({READ, MANAGE})


class PriceBookPermission:
    READ = "COMPANY_PRICE_BOOK_READ"
    MANAGE = "COMPANY_PRICE_BOOK_MANAGE"
    ACTIVATE = "COMPANY_PRICE_BOOK_ACTIVATE"

    ALL = frozenset({READ, MANAGE, ACTIVATE})


class CommunicationsPermission:
    READ = "COMPANY_COMMUNICATIONS_READ"
    MANAGE = "COMPANY_COMMUNICATIONS_MANAGE"

    ALL = frozenset({READ, MANAGE})


class EstimatePermission:
    READ = "COMPANY_ESTIMATE_READ"
    MANAGE = "COMPANY_ESTIMATE_MANAGE"

    ALL = frozenset({READ, MANAGE})


class EngineeringCommandPermission:
    READ = "COMPANY_ENGINEERING_COMMAND_READ"
    MANAGE = "COMPANY_ENGINEERING_COMMAND_MANAGE"
    APPROVE = "COMPANY_ENGINEERING_COMMAND_APPROVE"

    ALL = frozenset({READ, MANAGE, APPROVE})


class EngineeringExecutionPermission:
    REQUEST = "COMPANY_ENGINEERING_EXECUTION_REQUEST"

    ALL = frozenset({REQUEST})


class EngineeringCapacityPermission:
    READ = "COMPANY_ENGINEERING_CAPACITY_READ"
    MANAGE = "COMPANY_ENGINEERING_CAPACITY_MANAGE"

    ALL = frozenset({READ, MANAGE})


class EngineeringRepositoryOperationPermission:
    READ = "COMPANY_ENGINEERING_REPOSITORY_OPERATION_READ"
    EXECUTE = "COMPANY_ENGINEERING_REPOSITORY_OPERATION_EXECUTE"

    ALL = frozenset({READ, EXECUTE})


class WorkerControlPermission:
    MANAGE = "COMPANY_ENGINEERING_WORKER_MANAGE"

    ALL = frozenset({MANAGE})


class WorkerIdentityPermission:
    MANAGE = "COMPANY_WORKER_IDENTITY_MANAGE"

    ALL = frozenset({MANAGE})
