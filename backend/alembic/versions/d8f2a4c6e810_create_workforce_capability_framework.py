"""create workforce capability framework

Revision ID: d8f2a4c6e810
Revises: c6a1d3e5f709
"""

from collections.abc import Sequence

from alembic import op


revision: str = "d8f2a4c6e810"
down_revision: str | None = "c6a1d3e5f709"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_employees_company_id_id", "employees", ["company_id", "id"]
    )
    op.execute(_CREATE_SQL)


def downgrade() -> None:
    for table in (
        "workforce_language_capabilities",
        "workforce_languages",
        "workforce_profile_work_restrictions",
        "workforce_work_restrictions",
        "workforce_geographic_coverages",
        "workforce_branch_eligibilities",
        "workforce_profile_equipment_capabilities",
        "workforce_equipment_capabilities",
        "workforce_profile_certifications",
        "workforce_certifications",
        "workforce_profile_capabilities",
        "workforce_capabilities",
        "workforce_capability_categories",
        "workforce_capability_profiles",
    ):
        op.drop_table(table)
    op.drop_constraint("uq_employees_company_id_id", "employees", type_="unique")


_CREATE_SQL = r"""
CREATE TABLE workforce_capability_profiles (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, employee_id uuid NOT NULL,
 status varchar(20) NOT NULL, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_profiles_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profiles_employee FOREIGN KEY(company_id,employee_id) REFERENCES employees(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_profiles_company_employee UNIQUE(company_id,employee_id),
 CONSTRAINT uq_workforce_profiles_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_profiles_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_profiles_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_profiles_company_status ON workforce_capability_profiles(company_id,status,id);

CREATE TABLE workforce_capability_categories (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, code varchar(64) NOT NULL,
 display_name varchar(120) NOT NULL, description varchar(500), status varchar(20) NOT NULL,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_capability_categories_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_capability_categories_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_capability_categories_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_capability_categories_code CHECK(code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
 CONSTRAINT ck_workforce_capability_categories_name CHECK(length(btrim(display_name)) > 0),
 CONSTRAINT ck_workforce_capability_categories_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_capability_categories_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_capability_categories_company_status ON workforce_capability_categories(company_id,status,code);

CREATE TABLE workforce_capabilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, category_id uuid NOT NULL,
 code varchar(64) NOT NULL, display_name varchar(120) NOT NULL, description varchar(500),
 status varchar(20) NOT NULL, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_capabilities_category FOREIGN KEY(company_id,category_id) REFERENCES workforce_capability_categories(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_capabilities_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_capabilities_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_capabilities_code CHECK(code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
 CONSTRAINT ck_workforce_capabilities_name CHECK(length(btrim(display_name)) > 0),
 CONSTRAINT ck_workforce_capabilities_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_capabilities_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_capabilities_company_category ON workforce_capabilities(company_id,category_id,status,code);

CREATE TABLE workforce_profile_capabilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, capability_id uuid NOT NULL,
 proficiency varchar(20) NOT NULL, status varchar(20) NOT NULL, verified_at timestamptz,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_profile_capabilities_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profile_capabilities_capability FOREIGN KEY(company_id,capability_id) REFERENCES workforce_capabilities(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_profile_capabilities_profile_capability UNIQUE(profile_id,capability_id),
 CONSTRAINT ck_workforce_profile_capabilities_level CHECK(proficiency IN ('awareness','assisted','qualified','advanced','expert')),
 CONSTRAINT ck_workforce_profile_capabilities_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_profile_capabilities_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_profile_capabilities_company_capability ON workforce_profile_capabilities(company_id,capability_id,status,profile_id);

CREATE TABLE workforce_certifications (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, code varchar(64) NOT NULL,
 display_name varchar(120) NOT NULL, issuing_authority varchar(200), description varchar(500),
 status varchar(20) NOT NULL, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_certifications_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_certifications_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_certifications_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_certifications_code CHECK(code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
 CONSTRAINT ck_workforce_certifications_name CHECK(length(btrim(display_name)) > 0),
 CONSTRAINT ck_workforce_certifications_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_certifications_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_profile_certifications (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, certification_id uuid NOT NULL,
 credential_reference varchar(120) NOT NULL, status varchar(20) NOT NULL,
 issued_on date, expires_on date, verified_at timestamptz, verified_by_user_id uuid,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_profile_certifications_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profile_certifications_certification FOREIGN KEY(company_id,certification_id) REFERENCES workforce_certifications(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profile_certifications_verified_by FOREIGN KEY(verified_by_user_id) REFERENCES users(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_profile_certifications_credential UNIQUE(profile_id,certification_id,credential_reference),
 CONSTRAINT ck_workforce_profile_certifications_status CHECK(status IN ('pending','active','suspended','expired','revoked')),
 CONSTRAINT ck_workforce_profile_certifications_dates CHECK(expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on),
 CONSTRAINT ck_workforce_profile_certifications_verification CHECK((verified_at IS NULL) = (verified_by_user_id IS NULL)),
 CONSTRAINT ck_workforce_profile_certifications_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_profile_certifications_company_status ON workforce_profile_certifications(company_id,status,expires_on,profile_id);

CREATE TABLE workforce_equipment_capabilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, code varchar(64) NOT NULL,
 display_name varchar(120) NOT NULL, description varchar(500), status varchar(20) NOT NULL,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_equipment_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_equipment_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_equipment_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_equipment_code CHECK(code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
 CONSTRAINT ck_workforce_equipment_name CHECK(length(btrim(display_name)) > 0),
 CONSTRAINT ck_workforce_equipment_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_equipment_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_profile_equipment_capabilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, equipment_capability_id uuid NOT NULL,
 proficiency varchar(20) NOT NULL, status varchar(20) NOT NULL, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_profile_equipment_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profile_equipment_capability FOREIGN KEY(company_id,equipment_capability_id) REFERENCES workforce_equipment_capabilities(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_profile_equipment_profile_capability UNIQUE(profile_id,equipment_capability_id),
 CONSTRAINT ck_workforce_profile_equipment_level CHECK(proficiency IN ('awareness','assisted','qualified','advanced','expert')),
 CONSTRAINT ck_workforce_profile_equipment_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_profile_equipment_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_branch_eligibilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, branch_id uuid NOT NULL,
 status varchar(20) NOT NULL, starts_on date, ends_on date, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_branch_eligibilities_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_branch_eligibilities_branch FOREIGN KEY(company_id,branch_id) REFERENCES branches(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_branch_eligibilities_profile_branch UNIQUE(profile_id,branch_id),
 CONSTRAINT ck_workforce_branch_eligibilities_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_branch_eligibilities_dates CHECK(ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on),
 CONSTRAINT ck_workforce_branch_eligibilities_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_geographic_coverages (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL,
 coverage_type varchar(20) NOT NULL, coverage_code varchar(32) NOT NULL, status varchar(20) NOT NULL,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_geographic_coverages_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_geographic_coverages_profile_type_code UNIQUE(profile_id,coverage_type,coverage_code),
 CONSTRAINT ck_workforce_geographic_coverages_type CHECK(coverage_type IN ('postal_code','territory')),
 CONSTRAINT ck_workforce_geographic_coverages_code CHECK(coverage_code ~ '^[A-Za-z0-9][A-Za-z0-9 .-]{0,31}$'),
 CONSTRAINT ck_workforce_geographic_coverages_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_geographic_coverages_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_work_restrictions (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, code varchar(64) NOT NULL,
 display_name varchar(120) NOT NULL, description varchar(500), status varchar(20) NOT NULL,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_work_restrictions_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_work_restrictions_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_work_restrictions_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_work_restrictions_code CHECK(code ~ '^[a-z][a-z0-9_.-]{0,63}$'),
 CONSTRAINT ck_workforce_work_restrictions_name CHECK(length(btrim(display_name)) > 0),
 CONSTRAINT ck_workforce_work_restrictions_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_work_restrictions_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_profile_work_restrictions (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, restriction_id uuid NOT NULL,
 status varchar(20) NOT NULL, starts_on date, ends_on date, operational_note varchar(500),
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_profile_restrictions_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_profile_restrictions_definition FOREIGN KEY(company_id,restriction_id) REFERENCES workforce_work_restrictions(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_profile_restrictions_profile_definition_start UNIQUE(profile_id,restriction_id,starts_on),
 CONSTRAINT ck_workforce_profile_restrictions_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_profile_restrictions_dates CHECK(ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on),
 CONSTRAINT ck_workforce_profile_restrictions_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_languages (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, code varchar(35) NOT NULL,
 english_name varchar(120) NOT NULL, native_name varchar(120), status varchar(20) NOT NULL,
 concurrency_version integer NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_languages_company FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_languages_company_code UNIQUE(company_id,code),
 CONSTRAINT uq_workforce_languages_company_id UNIQUE(company_id,id),
 CONSTRAINT ck_workforce_languages_code CHECK(code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'),
 CONSTRAINT ck_workforce_languages_english_name CHECK(length(btrim(english_name)) > 0),
 CONSTRAINT ck_workforce_languages_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_languages_version CHECK(concurrency_version >= 1)
);

CREATE TABLE workforce_language_capabilities (
 id uuid PRIMARY KEY, company_id uuid NOT NULL, profile_id uuid NOT NULL, language_id uuid NOT NULL,
 spoken_proficiency varchar(20) NOT NULL, reading_proficiency varchar(20), writing_proficiency varchar(20),
 customer_facing_eligible boolean NOT NULL, interpreter_verified boolean NOT NULL,
 interpreter_verified_at timestamptz, status varchar(20) NOT NULL, concurrency_version integer NOT NULL,
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CONSTRAINT fk_workforce_language_capabilities_profile FOREIGN KEY(company_id,profile_id) REFERENCES workforce_capability_profiles(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT fk_workforce_language_capabilities_language FOREIGN KEY(company_id,language_id) REFERENCES workforce_languages(company_id,id) ON DELETE RESTRICT,
 CONSTRAINT uq_workforce_language_capabilities_profile_language UNIQUE(profile_id,language_id),
 CONSTRAINT ck_workforce_language_capabilities_spoken CHECK(spoken_proficiency IN ('basic','conversational','professional','fluent','native')),
 CONSTRAINT ck_workforce_language_capabilities_reading CHECK(reading_proficiency IS NULL OR reading_proficiency IN ('basic','conversational','professional','fluent','native')),
 CONSTRAINT ck_workforce_language_capabilities_writing CHECK(writing_proficiency IS NULL OR writing_proficiency IN ('basic','conversational','professional','fluent','native')),
 CONSTRAINT ck_workforce_language_capabilities_interpreter CHECK(NOT interpreter_verified OR interpreter_verified_at IS NOT NULL),
 CONSTRAINT ck_workforce_language_capabilities_status CHECK(status IN ('active','inactive')),
 CONSTRAINT ck_workforce_language_capabilities_version CHECK(concurrency_version >= 1)
);
CREATE INDEX ix_workforce_language_capabilities_company_language ON workforce_language_capabilities(company_id,language_id,status,profile_id);
"""
