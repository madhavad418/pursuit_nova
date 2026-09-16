import os
import re
from datetime import date, timedelta, datetime
from urllib.parse import urlparse

from argon2 import PasswordHasher
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, Float, Boolean, DateTime, LargeBinary,
    ForeignKey, UniqueConstraint, Index, create_engine, select, func, and_, or_, text, inspect
)
from sqlalchemy.engine import Engine
from sqlalchemy.sql import insert, update, delete

def normalize_database_url(url: str) -> str:
    """Hosted PostgreSQL (Railway and others) hands out postgres:// or postgresql:// URLs; this app ships the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./data/pursuitnova.db"))
if DATABASE_URL.startswith("sqlite:///./"):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rel = DATABASE_URL.replace("sqlite:///./", "", 1)
    abs_path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    DATABASE_URL = f"sqlite:///{abs_path}"

engine: Engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
metadata = MetaData()

roles = Table(
    "roles", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(80), unique=True, nullable=False),
    Column("scope_type", String(20), nullable=False, default="self"),
    Column("rank", Integer, nullable=False, default=100),
    Column("active", Boolean, nullable=False, default=True),
    # User id of the Admin who created the role; NULL for built-in and Super Admin roles shared by everyone.
    Column("created_by", Integer),
)
permissions = Table(
    "permissions", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(80), unique=True, nullable=False),
    Column("description", String(255), nullable=False),
)
role_permissions = Table(
    "role_permissions", metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)
users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(160), nullable=False),
    Column("email", String(190), unique=True, nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("role_id", ForeignKey("roles.id"), nullable=False),
    Column("manager_id", ForeignKey("users.id")),
    Column("title", String(160)),
    Column("region", String(80)),
    Column("category", String(80)),
    Column("active", Boolean, nullable=False, default=True),
    Column("mfa_enabled", Boolean, nullable=False, default=False),
    Column("mfa_secret", String(64)),
    Column("last_login_at", DateTime),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
companies = Table(
    "companies", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(220), nullable=False),
    Column("normalized_name", String(220), nullable=False),
    Column("vertical", Text, nullable=False),
    Column("website", String(500)),
    Column("domain", String(255)),
    Column("linkedin_url", String(500)),
    Column("external_url", String(500)),
    Column("region", String(80)),
    Column("country", String(100)),
    Column("state", String(100)),
    Column("city", String(100)),
    Column("remarks", Text),
    Column("status", String(40), nullable=False, default="Active"),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
contacts = Table(
    "contacts", metadata,
    Column("id", Integer, primary_key=True),
    Column("company_id", ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(180), nullable=False),
    Column("designation", String(180)),
    Column("department", String(120)),
    Column("email", String(190)),
    Column("normalized_email", String(190)),
    Column("phone", String(80)),
    Column("linkedin_url", String(500)),
    Column("location", String(220)),
    Column("remarks", Text),
    Column("is_primary", Boolean, nullable=False, default=False),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
leads = Table(
    "leads", metadata,
    Column("id", Integer, primary_key=True),
    Column("company_id", ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
    Column("owner_id", ForeignKey("users.id"), nullable=False),
    Column("temperature", String(20), nullable=False, default="Warm"),
    Column("source", String(80), nullable=False, default="LinkedIn"),
    Column("source_detail", String(255)),
    Column("status", String(60), nullable=False, default="New"),
    Column("region", String(80)),
    Column("country", String(100)),
    Column("state", String(100)),
    Column("city", String(100)),
    Column("next_follow_up", String(10)),
    Column("remarks", Text),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
meetings = Table(
    "meetings", metadata,
    Column("id", Integer, primary_key=True),
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="SET NULL")),
    Column("meeting_date", String(10), nullable=False),
    Column("meeting_time", String(10)),
    Column("meeting_type", String(80), nullable=False),
    Column("status", String(40), nullable=False, default="Scheduled"),
    Column("purpose", Text),
    Column("customer_participants", Text),
    Column("jsan_participants", Text),
    Column("remarks", Text),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
moms = Table(
    "moms", metadata,
    Column("id", Integer, primary_key=True),
    Column("meeting_id", ForeignKey("meetings.id", ondelete="SET NULL")),
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
    Column("summary", Text, nullable=False),
    Column("customer_requirements", Text),
    Column("jsan_commitments", Text),
    Column("customer_commitments", Text),
    Column("risks", Text),
    Column("next_steps", Text),
    Column("follow_up_date", String(10)),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
actions = Table(
    "actions", metadata,
    Column("id", Integer, primary_key=True),
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="SET NULL")),
    Column("action_date", String(10), nullable=False),
    Column("description", Text, nullable=False),
    Column("assigned_to", ForeignKey("users.id"), nullable=False),
    Column("due_date", String(10), nullable=False),
    Column("status", String(40), nullable=False, default="Open"),
    Column("priority", String(20), nullable=False, default="Medium"),
    Column("remarks", Text),
    Column("completion_date", String(10)),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
opportunities = Table(
    "opportunities", metadata,
    Column("id", Integer, primary_key=True),
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
    Column("company_id", ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),
    Column("owner_id", ForeignKey("users.id"), nullable=False),
    Column("presales_owner_id", ForeignKey("users.id")),
    Column("name", String(240), nullable=False),
    Column("service_practice", String(140)),
    Column("status", String(80), nullable=False, default="New Opportunity"),
    Column("forecast_category", String(20), nullable=False, default="Pipeline"),
    Column("amount", Float, nullable=False, default=0),
    Column("currency", String(10), nullable=False, default="USD"),
    Column("probability", Float, nullable=False, default=10),
    Column("weighted_value", Float, nullable=False, default=0),
    Column("expected_close_date", String(10)),
    Column("proposal_date", String(10)),
    Column("last_follow_up_date", String(10)),
    Column("next_follow_up_date", String(10)),
    Column("follow_up_count", Integer, nullable=False, default=0),
    Column("final_amount", Float),
    Column("lost_reason", String(255)),
    Column("hold_reason", String(255)),
    Column("hold_review_date", String(10)),
    Column("competitor", String(180)),
    Column("remarks", Text),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
    Column("closed_at", String(10)),
)
followups = Table(
    "followups", metadata,
    Column("id", Integer, primary_key=True),
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
    Column("follow_up_date", String(10), nullable=False),
    Column("owner_id", ForeignKey("users.id"), nullable=False),
    Column("response", Text),
    Column("next_follow_up_date", String(10)),
    Column("remarks", Text),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
opportunity_team = Table(
    "opportunity_team", metadata,
    Column("opportunity_id", ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("team_role", String(80), nullable=False, default="Contributor"),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
targets = Table(
    "targets", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("year", Integer, nullable=False),
    Column("quarter", String(2), nullable=False),
    Column("currency", String(10), nullable=False, default="USD"),
    Column("target_amount", Float, nullable=False, default=0),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
    UniqueConstraint("user_id", "year", "quarter", name="uq_target_user_period"),
)

org_settings = Table(
    "org_settings", metadata,
    Column("id", Integer, primary_key=True),
    Column("key", String(120), unique=True, nullable=False),
    Column("value", Text, nullable=False),
    Column("updated_by", ForeignKey("users.id")),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
fx_rates = Table(
    "fx_rates", metadata,
    Column("id", Integer, primary_key=True),
    Column("currency", String(10), unique=True, nullable=False),
    Column("rate_to_corporate", Float, nullable=False),
    Column("as_of", String(10), nullable=False),
    Column("source", String(120), nullable=False, default="MANUAL"),
    Column("updated_by", ForeignKey("users.id")),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
field_permissions = Table(
    "field_permissions", metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("entity_type", String(40), primary_key=True),
    Column("field_name", String(80), primary_key=True),
    Column("can_view", Boolean, nullable=False, default=True),
    Column("can_edit", Boolean, nullable=False, default=True),
)
saved_views = Table(
    "saved_views", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("module", String(40), nullable=False),
    Column("name", String(160), nullable=False),
    Column("filters_json", Text, nullable=False, default="{}"),
    Column("columns_json", Text, nullable=False, default="[]"),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
    UniqueConstraint("user_id", "module", "name", name="uq_saved_view_user_module_name"),
)
dashboard_preferences = Table(
    "dashboard_preferences", metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("widgets_json", Text, nullable=False, default="[]"),
    Column("layout_json", Text, nullable=False, default="{}"),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
microsoft_integrations = Table(
    "microsoft_integrations", metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("tenant_id", String(120)),
    Column("connected_email", String(190)),
    Column("scope", Text),
    Column("encrypted_refresh_token", Text),
    Column("connected_at", DateTime),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
documents = Table(
    "documents", metadata,
    Column("id", Integer, primary_key=True),
    Column("entity_type", String(40), nullable=False),
    Column("entity_id", Integer, nullable=False),
    Column("name", String(255), nullable=False),
    Column("document_type", String(80)),
    Column("url", String(1000), nullable=False),
    Column("version", String(40)),
    Column("description", Text),
    Column("uploaded_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
record_shares = Table(
    "record_shares", metadata,
    Column("id", Integer, primary_key=True),
    Column("entity_type", String(40), nullable=False),
    Column("entity_id", Integer, nullable=False),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("access_level", String(20), nullable=False, default="view"),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    UniqueConstraint("entity_type", "entity_id", "user_id", name="uq_record_share"),
)
notifications = Table(
    "notifications", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("notification_type", String(80), nullable=False),
    Column("title", String(255), nullable=False),
    Column("message", Text),
    Column("entity_type", String(40)),
    Column("entity_id", Integer),
    Column("due_date", String(10)),
    Column("severity", String(20), nullable=False, default="info"),
    Column("read_at", DateTime),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
workflow_rules = Table(
    "workflow_rules", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(80), unique=True, nullable=False),
    Column("name", String(180), nullable=False),
    Column("description", Text),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("config_json", Text),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)
master_values = Table(
    "master_values", metadata,
    Column("id", Integer, primary_key=True),
    Column("category", String(80), nullable=False),
    Column("value", String(180), nullable=False),
    Column("sort_order", Integer, nullable=False, default=100),
    Column("active", Boolean, nullable=False, default=True),
    UniqueConstraint("category", "value", name="uq_master_value"),
)
audit_logs = Table(
    "audit_logs", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id")),
    Column("entity_type", String(60), nullable=False),
    Column("entity_id", Integer),
    Column("action", String(80), nullable=False),
    Column("details", Text),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
security_logs = Table(
    "security_logs", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id")),
    Column("event_type", String(80), nullable=False),
    Column("success", Boolean, nullable=False, default=True),
    Column("ip_address", String(80)),
    Column("user_agent", String(500)),
    Column("details", Text),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
revoked_sessions = Table(
    "revoked_sessions", metadata,
    Column("jti", String(80), primary_key=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("revoked_at", DateTime, server_default=func.current_timestamp()),
)

# Word documents attached to a Minutes of Meeting. Stored in the database because the app host's disk is not persistent.
mom_attachments = Table(
    "mom_attachments", metadata,
    Column("id", Integer, primary_key=True),
    Column("mom_id", ForeignKey("moms.id", ondelete="CASCADE"), nullable=False),
    Column("lead_id", ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("data", LargeBinary, nullable=False),
    Column("uploaded_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)

# Work items that are not tied to a prospect (PPT preparation, summit preparation, internal tasks)
generic_actions = Table(
    "generic_actions", metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(255), nullable=False),
    Column("action_type", String(60), nullable=False, default="Other"),
    Column("description", Text),
    Column("assigned_to", ForeignKey("users.id"), nullable=False),
    Column("due_date", String(10), nullable=False),
    Column("status", String(40), nullable=False, default="Open"),
    Column("priority", String(20), nullable=False, default="Medium"),
    Column("remarks", Text),
    Column("completion_date", String(10)),
    Column("created_by", ForeignKey("users.id"), nullable=False),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
)

kpi_templates = Table(
    "kpi_templates", metadata,
    Column("id", Integer, primary_key=True),
    Column("category", String(80), nullable=False),
    Column("kra", String(255), nullable=False),
    Column("kpi", String(255), nullable=False),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("active", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
)
kpi_targets = Table(
    "kpi_targets", metadata,
    Column("id", Integer, primary_key=True),
    Column("template_id", ForeignKey("kpi_templates.id", ondelete="CASCADE"), nullable=False),
    Column("month", String(7), nullable=False),
    Column("target_value", Float, nullable=False, default=0),
    Column("created_by", ForeignKey("users.id")),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
    UniqueConstraint("template_id", "month", name="uq_kpi_target_tpl_month"),
)
kpi_actuals = Table(
    "kpi_actuals", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("template_id", ForeignKey("kpi_templates.id", ondelete="CASCADE"), nullable=False),
    Column("month", String(7), nullable=False),
    Column("actual_value", Float, nullable=False, default=0),
    Column("remarks", Text),
    Column("status", String(20), nullable=False, default="draft"),
    Column("reviewed_by", ForeignKey("users.id")),
    Column("review_remarks", Text),
    Column("reviewed_at", DateTime),
    Column("created_at", DateTime, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, server_default=func.current_timestamp()),
    UniqueConstraint("user_id", "template_id", "month", name="uq_kpi_actual_user_tpl_month"),
)

Index("ix_leads_owner", leads.c.owner_id)
Index("ix_leads_company", leads.c.company_id)
Index("ix_actions_assignee_due", actions.c.assigned_to, actions.c.due_date)
Index("ix_mom_attachments_mom", mom_attachments.c.mom_id)
Index("ix_generic_actions_assignee_due", generic_actions.c.assigned_to, generic_actions.c.due_date)
Index("ix_opps_owner_status", opportunities.c.owner_id, opportunities.c.status)
Index("ix_companies_norm", companies.c.normalized_name)
Index("ix_companies_domain", companies.c.domain)
Index("ix_contacts_email", contacts.c.normalized_email)
Index("ix_saved_views_user_module", saved_views.c.user_id, saved_views.c.module)
Index("ix_fx_currency", fx_rates.c.currency)

PH = PasswordHasher()

def hash_password(password: str) -> str:
    return PH.hash(password)

def verify_password(password: str, encoded: str) -> bool:
    try:
        return PH.verify(encoded, password)
    except Exception:
        return False

def normalize_name(value: str | None) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"\b(pvt\.?\s*ltd\.?|private limited|limited|ltd\.?|inc\.?|llc|corp\.?|corporation|gmbh|plc)\b", "", value)
    return re.sub(r"[^a-z0-9]+", "", value)

def normalize_email(value: str | None) -> str | None:
    v = (value or "").strip().lower()
    return v or None

def domain_from_url(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if "//" not in v:
        v = "https://" + v
    try:
        host = (urlparse(v).hostname or "").lower()
        return host[4:] if host.startswith("www.") else (host or None)
    except Exception:
        return None

def dictrow(r):
    return dict(r._mapping) if r is not None else None

def rows(stmt, params=None):
    with engine.connect() as c:
        res = c.execute(stmt, params or {})
        return [dictrow(r) for r in res.fetchall()]

def row(stmt, params=None):
    with engine.connect() as c:
        return dictrow(c.execute(stmt, params or {}).fetchone())

def execute(stmt, params=None):
    with engine.begin() as c:
        res = c.execute(stmt, params or {})
        try:
            return res.inserted_primary_key[0]
        except Exception:
            return None

def init_db(seed_demo: bool | None = None, create_schema: bool = True):
    """Prepare the database. Reference data (roles, permissions, settings) is always ensured; demo content only on request."""
    if create_schema:
        metadata.create_all(engine)
    _add_missing_columns()
    if seed_demo is None:
        production = os.getenv("APP_ENV", "development").lower() == "production"
        seed_demo = os.getenv("SEED_DEMO", "false" if production else "true").lower() == "true"
    _seed_reference()
    if seed_demo:
        _seed_demo_accounts()
    _bootstrap_initial_admin()
    if os.getenv("SEED_DEMO_DATA", "false").lower() == "true":
        _seed_demo_business()
    _migrate_hierarchy_scopes()
    try:
        _seed_kpi_templates()
    except Exception:
        pass  # Table may not exist yet if schema is managed externally

def _bootstrap_initial_admin():
    """First start of an empty production database: create one Super Admin from INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_PASSWORD."""
    email = (os.getenv("INITIAL_ADMIN_EMAIL") or "").strip().lower(); pwd = os.getenv("INITIAL_ADMIN_PASSWORD") or ""
    if not email or not pwd:
        return
    with engine.begin() as c:
        if c.execute(select(func.count()).select_from(users)).scalar_one():
            return
        role_id = c.execute(select(roles.c.id).where(roles.c.name == "Super Admin")).scalar()
        c.execute(insert(users).values(name=os.getenv("INITIAL_ADMIN_NAME") or "Super Admin", email=email, password_hash=hash_password(pwd),
                                       role_id=role_id, title="Super Administrator", region="Global", active=True))

def _add_missing_columns():
    """create_all() never alters existing tables, so add columns introduced after a database was first created."""
    # Ensure new tables exist (safe even if AUTO_CREATE_SCHEMA=false)
    for tbl in (kpi_templates, kpi_targets, kpi_actuals, generic_actions, mom_attachments):
        tbl.create(engine, checkfirst=True)
    if "created_by" not in {c["name"] for c in inspect(engine).get_columns("roles")}:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE roles ADD COLUMN created_by INTEGER"))
    if "category" not in {c["name"] for c in inspect(engine).get_columns("users")}:
        with engine.begin() as c:
            c.execute(text("ALTER TABLE users ADD COLUMN category VARCHAR(80)"))
    # Vertical is free text of any length (widening a column keeps every existing value as it is)
    vcol = next(c for c in inspect(engine).get_columns("companies") if c["name"] == "vertical")
    if engine.dialect.name == "postgresql" and getattr(vcol["type"], "length", None):
        with engine.begin() as c:
            c.execute(text("ALTER TABLE companies ALTER COLUMN vertical TYPE TEXT"))

def _migrate_hierarchy_scopes():
    """One-time move of Admin/Director from organisation-wide to hierarchy scope, so only Super Admins see everything."""
    with engine.begin() as c:
        if c.execute(select(org_settings.c.id).where(org_settings.c.key == "rbac_hierarchy_scopes")).first():
            return
        c.execute(update(roles).where(and_(roles.c.name.in_(["Admin", "Director"]), roles.c.scope_type == "all")).values(scope_type="team"))
        c.execute(insert(org_settings).values(key="rbac_hierarchy_scopes", value="applied"))

def _seed_reference():
    """Roles, permissions and settings every deployment needs, demo or production. Only fills empty tables."""
    with engine.begin() as c:
        if c.execute(select(func.count()).select_from(roles)).scalar_one() == 0:
            role_defs = [
                ("Super Admin", "all", 1), ("Admin", "team", 2), ("Director", "team", 10),
                ("BD Manager", "team", 20), ("BD Lead", "team", 30), ("BD Executive", "self", 40),
                ("Presales Lead", "assigned", 35),
            ]
            c.execute(insert(roles), [{"name": n, "scope_type": s, "rank": r} for n, s, r in role_defs])
        perm_defs = {
            "LEAD_VIEW":"View permitted leads", "LEAD_CREATE":"Create leads", "LEAD_EDIT":"Edit permitted leads", "LEAD_REASSIGN":"Reassign leads",
            "COMPANY_VIEW":"View company master", "COMPANY_EDIT":"Create/edit company master", "COMPANY_MERGE":"Merge duplicate companies",
            "CONTACT_EDIT":"Create/edit contacts", "MEETING_EDIT":"Manage meetings and MoM", "ACTION_EDIT":"Create/update actions",
            "OPPORTUNITY_VIEW":"View permitted opportunities", "OPPORTUNITY_EDIT":"Create/update opportunities", "OPPORTUNITY_CLOSE":"Close opportunities",
            "FORECAST_VIEW":"View forecasts", "TARGET_EDIT":"Manage targets", "REPORT_VIEW":"View reports", "DOCUMENT_EDIT":"Attach document metadata",
            "USER_ADMIN":"Manage users", "ROLE_ADMIN":"Manage role permissions", "AUDIT_VIEW":"View business/security audit", "DATA_EXPORT":"Export CRM data",
            "WORKFLOW_ADMIN":"Manage workflow rules", "SHARE_RECORD":"Share records explicitly"
        }
        if c.execute(select(func.count()).select_from(permissions)).scalar_one() == 0:
            c.execute(insert(permissions), [{"code": k, "description": v} for k,v in perm_defs.items()])
        role_map = {r.name: r.id for r in c.execute(select(roles.c.id, roles.c.name)).fetchall()}
        perm_map = {r.code: r.id for r in c.execute(select(permissions.c.id, permissions.c.code)).fetchall()}
        allp = set(perm_defs)
        mappings = {
            "Super Admin": allp,
            "Admin": allp,
            "Director": allp - {"USER_ADMIN","ROLE_ADMIN","WORKFLOW_ADMIN"},
            "BD Manager": {"LEAD_VIEW","LEAD_CREATE","LEAD_EDIT","LEAD_REASSIGN","COMPANY_VIEW","COMPANY_EDIT","CONTACT_EDIT","MEETING_EDIT","ACTION_EDIT","OPPORTUNITY_VIEW","OPPORTUNITY_EDIT","OPPORTUNITY_CLOSE","FORECAST_VIEW","TARGET_EDIT","REPORT_VIEW","DOCUMENT_EDIT","SHARE_RECORD"},
            "BD Lead": {"LEAD_VIEW","LEAD_CREATE","LEAD_EDIT","LEAD_REASSIGN","COMPANY_VIEW","COMPANY_EDIT","CONTACT_EDIT","MEETING_EDIT","ACTION_EDIT","OPPORTUNITY_VIEW","OPPORTUNITY_EDIT","OPPORTUNITY_CLOSE","FORECAST_VIEW","REPORT_VIEW","DOCUMENT_EDIT","SHARE_RECORD"},
            "BD Executive": {"LEAD_VIEW","LEAD_CREATE","LEAD_EDIT","COMPANY_VIEW","COMPANY_EDIT","CONTACT_EDIT","MEETING_EDIT","ACTION_EDIT","OPPORTUNITY_VIEW","OPPORTUNITY_EDIT","OPPORTUNITY_CLOSE","FORECAST_VIEW","REPORT_VIEW","DOCUMENT_EDIT"},
            "Presales Lead": {"LEAD_VIEW","COMPANY_VIEW","MEETING_EDIT","ACTION_EDIT","OPPORTUNITY_VIEW","OPPORTUNITY_EDIT","FORECAST_VIEW","REPORT_VIEW","DOCUMENT_EDIT"},
        }
        existing = c.execute(select(func.count()).select_from(role_permissions)).scalar_one()
        if existing == 0:
            payload=[]
            for rn, codes in mappings.items():
                for code in codes:
                    payload.append({"role_id":role_map[rn],"permission_id":perm_map[code]})
            c.execute(insert(role_permissions), payload)

        if c.execute(select(func.count()).select_from(field_permissions)).scalar_one() == 0:
            sensitive = {
                "contact": ["email","phone","linkedin_url","remarks"],
                "opportunity": ["amount","currency","probability","weighted_value","final_amount","competitor","remarks"],
            }
            fp=[]
            for rn, rid in role_map.items():
                for entity, fields in sensitive.items():
                    for field in fields:
                        can_view=True; can_edit=True
                        if rn=="Presales Lead":
                            if entity=="opportunity" and field=="final_amount": can_view=False; can_edit=False
                            elif entity=="opportunity" and field in {"amount","currency","weighted_value"}: can_edit=False
                            elif entity=="contact": can_edit=False
                        fp.append({"role_id":rid,"entity_type":entity,"field_name":field,"can_view":can_view,"can_edit":can_edit})
            c.execute(insert(field_permissions), fp)
        _seed_settings(c)

def _seed_demo_accounts():
    """Demo team plus the named JSAN administrators, all using SEED_DEMO_PASSWORD. Development only."""
    with engine.begin() as c:
        role_map = {r.name: r.id for r in c.execute(select(roles.c.id, roles.c.name)).fetchall()}
        if c.execute(select(func.count()).select_from(users)).scalar_one() == 0:
            pwd = os.getenv("SEED_DEMO_PASSWORD", "PursuitNovaDemo@2026")
            seed_users = [
                ("JSAN Super Admin", "superadmin@jsan.local", "Super Admin", None, "Platform Owner", "Global"),
                ("JSAN Admin", "admin@jsan.local", "Admin", 1, "CRM Administrator", "Global"),
                ("Growth Director", "director@jsan.local", "Director", 2, "Director - Growth", "Global"),
                ("BD Manager", "bd.manager@jsan.local", "BD Manager", 3, "Business Development Manager", "Global"),
                ("BD Lead", "bd.lead@jsan.local", "BD Lead", 4, "Business Development Lead", "North America"),
                ("BD Executive A", "bd.exec1@jsan.local", "BD Executive", 5, "Business Development Executive", "North America"),
                ("BD Executive B", "bd.exec2@jsan.local", "BD Executive", 5, "Business Development Executive", "Europe"),
                ("Presales Lead", "presales@jsan.local", "Presales Lead", 3, "Presales Lead", "Global"),
            ]
            for name,email,rn,manager_id,title,region in seed_users:
                c.execute(insert(users).values(name=name,email=email,password_hash=hash_password(pwd),role_id=role_map[rn],manager_id=manager_id,title=title,region=region,active=True))

        # Named JSAN administrators. Inserted by email so existing databases pick them up on next start.
        pwd = os.getenv("SEED_DEMO_PASSWORD", "PursuitNovaDemo@2026")
        named_admins = [
            ("Ram Reddy", "rreddy@jsanconsulting.com", "Super Admin", None, "Super Administrator", "Global"),
            ("Kamalakar", "kdasari@jsanconsulting.com", "Super Admin", None, "Super Administrator", "Global"),
            ("Chandrika", "chandrika@jsan.local", "Admin", "rreddy@jsanconsulting.com", "Administrator", "Global"),
            ("Satish", "vsatish@jsanconsulting.com", "Admin", "rreddy@jsanconsulting.com", "Administrator", "Global"),
            ("Santosh", "santoshpanda@jsanconsulting.com", "Admin", "rreddy@jsanconsulting.com", "Administrator", "Global"),
        ]
        for name,email,rn,manager_email,title,region in named_admins:
            if c.execute(select(users.c.id).where(users.c.email==email)).first(): continue
            manager_id = c.execute(select(users.c.id).where(users.c.email==manager_email)).scalar() if manager_email else None
            c.execute(insert(users).values(name=name,email=email,password_hash=hash_password(pwd),role_id=role_map[rn],manager_id=manager_id,title=title,region=region,active=True))

def _seed_demo_business():
    """Sample companies, prospects and pipeline for demos and tests (SEED_DEMO_DATA=true). Refers to the demo team by id."""
    with engine.begin() as c:
        demo_team = c.execute(select(users.c.id).where(users.c.email == "bd.exec1@jsan.local")).first()
        if demo_team and c.execute(select(func.count()).select_from(companies)).scalar_one() == 0:
            today = date.today()
            company_payload = [
                {"name":"Northstar Mobility","vertical":"Automotive & Mobility","website":"https://northstar.example","linkedin_url":"https://linkedin.com/company/northstar-example","region":"North America","country":"USA","state":"California","city":"San Francisco","remarks":"Strategic mobility account","created_by":6},
                {"name":"Helix Telecom","vertical":"Telecommunications","website":"https://helix.example","linkedin_url":"https://linkedin.com/company/helix-example","region":"Europe","country":"UK","state":"England","city":"London","remarks":"Managed services discussion","created_by":7},
                {"name":"Aster Data Systems","vertical":"Data & AI","website":"https://aster.example","linkedin_url":"https://linkedin.com/company/aster-example","region":"North America","country":"USA","state":"Washington","city":"Seattle","remarks":"GeoAI and data operations prospect","created_by":6},
                {"name":"Cobalt Retail Group","vertical":"Retail","website":"https://cobalt.example","region":"Europe","country":"Germany","state":"Berlin","city":"Berlin","remarks":"Retail analytics opportunity","created_by":7},
            ]
            for p in company_payload:
                p["normalized_name"] = normalize_name(p["name"]); p["domain"] = domain_from_url(p.get("website")); c.execute(insert(companies).values(**p))
            contact_payload = [
                {"company_id":1,"name":"Alex Morgan","designation":"Senior Program Manager","department":"Operations","email":"alex@northstar.example","phone":"+1 415 555 0101","linkedin_url":"https://linkedin.com/in/alex-example","location":"San Francisco","remarks":"Primary business contact","is_primary":True,"created_by":6},
                {"company_id":1,"name":"Taylor Reed","designation":"Director Procurement","department":"Procurement","email":"taylor@northstar.example","phone":"+1 415 555 0102","location":"San Francisco","remarks":"Commercial stakeholder","is_primary":False,"created_by":6},
                {"company_id":2,"name":"Emma Clarke","designation":"Head of Network Operations","department":"Operations","email":"emma@helix.example","phone":"+44 20 7946 0111","location":"London","remarks":"Technical decision maker","is_primary":True,"created_by":7},
                {"company_id":3,"name":"Jordan Lee","designation":"VP Data Platforms","department":"Technology","email":"jordan@aster.example","phone":"+1 206 555 0151","location":"Seattle","remarks":"Executive sponsor","is_primary":True,"created_by":6},
                {"company_id":4,"name":"Lena Fischer","designation":"Director Digital","department":"Technology","email":"lena@cobalt.example","phone":"+49 30 555 0199","location":"Berlin","remarks":"Digital transformation owner","is_primary":True,"created_by":7},
            ]
            for p in contact_payload:
                p["normalized_email"] = normalize_email(p.get("email")); c.execute(insert(contacts).values(**p))
            lead_payload = [
                {"company_id":1,"owner_id":6,"temperature":"Hot","source":"Referral","source_detail":"Leadership introduction","status":"Qualified","region":"North America","country":"USA","state":"California","city":"San Francisco","next_follow_up":(today+timedelta(days=1)).isoformat(),"remarks":"Customer requested operating model and commercials","created_by":6},
                {"company_id":2,"owner_id":7,"temperature":"Warm","source":"LinkedIn","source_detail":"Direct outreach","status":"Engaged","region":"Europe","country":"UK","state":"England","city":"London","next_follow_up":today.isoformat(),"remarks":"Awaiting next technical discussion","created_by":7},
                {"company_id":3,"owner_id":6,"temperature":"Hot","source":"Conference","source_detail":"GeoAI Summit 2026","status":"Qualified","region":"North America","country":"USA","state":"Washington","city":"Seattle","next_follow_up":(today+timedelta(days=3)).isoformat(),"remarks":"Strong GeoAI use case","created_by":6},
                {"company_id":4,"owner_id":7,"temperature":"Cold","source":"Event","source_detail":"Retail Tech Europe","status":"Contacted","region":"Europe","country":"Germany","state":"Berlin","city":"Berlin","next_follow_up":(today+timedelta(days=7)).isoformat(),"remarks":"Early stage","created_by":7},
            ]
            c.execute(insert(leads), lead_payload)
            c.execute(insert(meetings), [
                {"lead_id":1,"meeting_date":(today-timedelta(days=2)).isoformat(),"meeting_time":"10:30","meeting_type":"Discovery","status":"Completed","purpose":"Understand field operations scope","customer_participants":"Alex Morgan; Taylor Reed","jsan_participants":"BD Executive A; BD Lead","remarks":"Positive discussion; commercial model requested","created_by":6},
                {"lead_id":2,"meeting_date":(today-timedelta(days=1)).isoformat(),"meeting_time":"15:00","meeting_type":"Technical Discussion","status":"Completed","purpose":"Review managed service capability","customer_participants":"Emma Clarke","jsan_participants":"BD Executive B; Presales Lead","remarks":"Need sample SLA and staffing model","created_by":7},
            ])
            c.execute(insert(moms), {"meeting_id":1,"lead_id":1,"summary":"Customer is evaluating a multi-region field operations partner.","customer_requirements":"Coverage model, governance, weekly KPI reporting, commercial flexibility","jsan_commitments":"Share operating model and indicative commercials","customer_commitments":"Confirm target countries and monthly volumes","risks":"Volume assumptions are still preliminary","next_steps":"Send capability pack and schedule commercial review","follow_up_date":(today+timedelta(days=1)).isoformat(),"created_by":6})
            c.execute(insert(actions), [
                {"lead_id":1,"action_date":today.isoformat(),"description":"Share operating model and indicative commercials","assigned_to":6,"due_date":(today+timedelta(days=1)).isoformat(),"status":"In Progress","priority":"High","remarks":"Draft under review","created_by":5},
                {"lead_id":1,"action_date":today.isoformat(),"description":"Validate pricing assumptions","assigned_to":8,"due_date":(today+timedelta(days=2)).isoformat(),"status":"Open","priority":"High","remarks":"Presales input required","created_by":5},
                {"lead_id":2,"action_date":(today-timedelta(days=2)).isoformat(),"description":"Share SLA and staffing model","assigned_to":7,"due_date":(today-timedelta(days=1)).isoformat(),"status":"Open","priority":"High","remarks":"Overdue customer commitment","created_by":5},
            ])
            opps = [
                {"lead_id":1,"company_id":1,"owner_id":6,"presales_owner_id":8,"name":"Northstar Field Operations Managed Service","service_practice":"Managed Services","status":"Awaiting Response","forecast_category":"Best Case","amount":650000,"currency":"USD","probability":65,"weighted_value":422500,"expected_close_date":(today+timedelta(days=20)).isoformat(),"proposal_date":(today-timedelta(days=4)).isoformat(),"last_follow_up_date":(today-timedelta(days=2)).isoformat(),"next_follow_up_date":(today+timedelta(days=1)).isoformat(),"follow_up_count":2,"competitor":"Competitor A","remarks":"Commercial review pending","created_by":6},
                {"lead_id":3,"company_id":3,"owner_id":6,"presales_owner_id":8,"name":"Aster GeoAI Platform Services","service_practice":"GeoAI / Data","status":"Presales / Solutioning","forecast_category":"Pipeline","amount":320000,"currency":"USD","probability":45,"weighted_value":144000,"expected_close_date":(today+timedelta(days=35)).isoformat(),"last_follow_up_date":today.isoformat(),"next_follow_up_date":(today+timedelta(days=3)).isoformat(),"follow_up_count":1,"remarks":"Demo and solution definition in progress","created_by":6},
                {"lead_id":2,"company_id":2,"owner_id":7,"presales_owner_id":8,"name":"Helix Telecom Service Desk","service_practice":"IT Managed Services","status":"Proposal Submitted","forecast_category":"Best Case","amount":410000,"currency":"USD","probability":55,"weighted_value":225500,"expected_close_date":(today+timedelta(days=15)).isoformat(),"proposal_date":(today-timedelta(days=3)).isoformat(),"last_follow_up_date":(today-timedelta(days=1)).isoformat(),"next_follow_up_date":today.isoformat(),"follow_up_count":1,"competitor":"Competitor B","remarks":"Awaiting feedback on staffing model","created_by":7},
            ]
            for opp in opps:
                c.execute(insert(opportunities).values(**opp))
            # Historical demo outcomes keep executive analytics visually meaningful across periods.
            historical = [
                {"lead_id":1,"company_id":1,"owner_id":6,"name":"Northstar Mobility Discovery Phase","service_practice":"Managed Services","status":"Closed Won","forecast_category":"Closed","amount":185000,"final_amount":178000,"currency":"USD","probability":100,"weighted_value":178000,"expected_close_date":(today-timedelta(days=60)).isoformat(),"closed_at":(today-timedelta(days=58)).isoformat(),"created_at":datetime.combine(today-timedelta(days=125), datetime.min.time()),"remarks":"Earlier discovery workstream won","created_by":6},
                {"lead_id":2,"company_id":2,"owner_id":7,"name":"Helix Network Assessment","service_practice":"Telecommunications","status":"Closed Won","forecast_category":"Closed","amount":140000,"final_amount":136000,"currency":"USD","probability":100,"weighted_value":136000,"expected_close_date":(today-timedelta(days=145)).isoformat(),"closed_at":(today-timedelta(days=142)).isoformat(),"created_at":datetime.combine(today-timedelta(days=210), datetime.min.time()),"remarks":"Assessment engagement won","created_by":7},
                {"lead_id":3,"company_id":3,"owner_id":6,"name":"Aster Data Quality Pilot","service_practice":"Data & AI","status":"Closed Lost","forecast_category":"Closed","amount":95000,"currency":"USD","probability":0,"weighted_value":0,"lost_reason":"Budget Not Approved","expected_close_date":(today-timedelta(days=225)).isoformat(),"closed_at":(today-timedelta(days=220)).isoformat(),"created_at":datetime.combine(today-timedelta(days=285), datetime.min.time()),"remarks":"Pilot deferred by customer","created_by":6},
                {"lead_id":4,"company_id":4,"owner_id":7,"name":"Cobalt Retail Analytics Pilot","service_practice":"Data & AI","status":"Closed Won","forecast_category":"Closed","amount":120000,"final_amount":115000,"currency":"USD","probability":100,"weighted_value":115000,"expected_close_date":(today-timedelta(days=310)).isoformat(),"closed_at":(today-timedelta(days=304)).isoformat(),"created_at":datetime.combine(today-timedelta(days=365), datetime.min.time()),"remarks":"Initial analytics pilot","created_by":7},
                {"lead_id":1,"company_id":1,"owner_id":6,"name":"Northstar Field Validation Pilot","service_practice":"Field Operations","status":"Closed Won","forecast_category":"Closed","amount":210000,"final_amount":205000,"currency":"USD","probability":100,"weighted_value":205000,"expected_close_date":(today-timedelta(days=395)).isoformat(),"closed_at":(today-timedelta(days=390)).isoformat(),"created_at":datetime.combine(today-timedelta(days=455), datetime.min.time()),"remarks":"Field validation pilot","created_by":6},
            ]
            for opp in historical:
                c.execute(insert(opportunities).values(**opp))
            c.execute(insert(opportunity_team), [
                {"opportunity_id":1,"user_id":8,"team_role":"Presales Owner","created_by":6},
                {"opportunity_id":2,"user_id":8,"team_role":"Presales Owner","created_by":6},
                {"opportunity_id":3,"user_id":8,"team_role":"Presales Owner","created_by":7},
            ])
            c.execute(insert(followups), [
                {"opportunity_id":1,"follow_up_date":(today-timedelta(days=6)).isoformat(),"owner_id":6,"response":"Customer reviewing scope","next_follow_up_date":(today-timedelta(days=2)).isoformat(),"remarks":"Requested additional pricing detail","created_by":6},
                {"opportunity_id":1,"follow_up_date":(today-timedelta(days=2)).isoformat(),"owner_id":6,"response":"No final response yet","next_follow_up_date":(today+timedelta(days=1)).isoformat(),"remarks":"Follow-up with procurement","created_by":6},
            ])
            c.execute(insert(targets), [
                {"user_id":6,"year":today.year,"quarter":f"Q{((today.month-1)//3)+1}","currency":"USD","target_amount":500000,"created_by":4},
                {"user_id":7,"year":today.year,"quarter":f"Q{((today.month-1)//3)+1}","currency":"USD","target_amount":450000,"created_by":4},
                {"user_id":5,"year":today.year,"quarter":f"Q{((today.month-1)//3)+1}","currency":"USD","target_amount":950000,"created_by":4},
            ])


def _seed_settings(c):
    # updated_by stays NULL: on a fresh production database no user exists yet for the foreign key to point at.
    if c.execute(select(func.count()).select_from(org_settings)).scalar_one() == 0:
        c.execute(insert(org_settings), [
            {"key":"corporate_currency","value":os.getenv("CORPORATE_CURRENCY","USD").upper(),"updated_by":None},
            {"key":"product_name","value":"JSAN PursuitNova","updated_by":None},
        ])
    if c.execute(select(func.count()).select_from(fx_rates)).scalar_one() == 0:
        today_iso=date.today().isoformat()
        c.execute(insert(fx_rates), [
            {"currency":"USD","rate_to_corporate":1.0,"as_of":today_iso,"source":"DEFAULT","updated_by":None},
            {"currency":"INR","rate_to_corporate":0.012,"as_of":today_iso,"source":"DEFAULT","updated_by":None},
            {"currency":"GBP","rate_to_corporate":1.27,"as_of":today_iso,"source":"DEFAULT","updated_by":None},
            {"currency":"EUR","rate_to_corporate":1.09,"as_of":today_iso,"source":"DEFAULT","updated_by":None},
        ])

    if c.execute(select(func.count()).select_from(master_values)).scalar_one() == 0:
        masters = {
            "Lead Source":["LinkedIn","Referral","Event","Conference","Website","Existing Customer","Partner","Management Reference","Outbound","RFP / Tender","Other"],
            "Temperature":["Hot","Warm","Cold"],
            "Region":["North America","Europe","UK","Middle East","APAC","India","ANZ","Africa","LATAM"],
            "Vertical":["Telecommunications","GIS / Geospatial","Data & AI","Automotive & Mobility","IT Services","Managed Services","Healthcare","Retail","Government","Utilities","Other"],
            "Action Status":["Open","In Progress","Pending Customer","Pending Internal","Completed","Cancelled"],
            "Action Priority":["Critical","High","Medium","Low"],
        }
        items=[]
        for cat, vals in masters.items():
            for idx, val in enumerate(vals): items.append({"category":cat,"value":val,"sort_order":idx})
        c.execute(insert(master_values), items)
    if c.execute(select(func.count()).select_from(workflow_rules)).scalar_one() == 0:
        c.execute(insert(workflow_rules), [
                {"code":"ACTION_OVERDUE","name":"Overdue action alert","description":"Notify assignee and management when an action is overdue.","enabled":True,"config_json":"{\"escalate_after_days\":2}"},
                {"code":"AWAITING_RESPONSE","name":"Awaiting response follow-up","description":"Create reminder when an opportunity awaits customer response.","enabled":True,"config_json":"{\"days\":3}"},
                {"code":"HOT_LEAD_INACTIVITY","name":"Hot lead inactivity","description":"Escalate hot leads without activity.","enabled":True,"config_json":"{\"days\":7}"},
                {"code":"CLOSE_DATE","name":"Expected close reminder","description":"Alert owner before expected close date.","enabled":True,"config_json":"{\"days\":7}"},
            ])

def _seed_kpi_templates():
    """Seed KRA/KPI template definitions for all 3 categories. Only fills if kpi_templates is empty."""
    with engine.begin() as c:
        if c.execute(select(func.count()).select_from(kpi_templates)).scalar_one() > 0:
            return
        BD_KRA1 = "Market research and analysis for BD - Conduct, market research and competetive ananlysis to idenitfy trend, risk and growth opportunities"
        BD_KRA2 = "Sales Pipeline Management; Build, manage and optimize the sale pipeline to continue the deal flow and predicitble revenue"
        BD_KRA3 = "Proposal, Negotiation/ Partnership and Deal Closure"
        BD_KRA4 = "Brand, Positioning and Business Promotions"
        tpls = [
            # Business Development Lead (Excel Section 1 — Saumya)
            ("Business Development Lead",BD_KRA1, "New opportunities, newsletters, new trends, market updates", 1),
            ("Business Development Lead",BD_KRA1, "Identify prospects; email campaign", 2),
            ("Business Development Lead",BD_KRA2, "Qualified sales opportunities created", 3),
            ("Business Development Lead",BD_KRA2, "Lead to deal conversion", 4),
            ("Business Development Lead",BD_KRA3, "Proposal to closure conversion rate", 5),
            ("Business Development Lead",BD_KRA3, "No of New Strategic Partnership Signed", 6),
            ("Business Development Lead",BD_KRA3, "RFP / RFQ opportunities identified/ Participation", 7),
            ("Business Development Lead",BD_KRA4, "No of Industry events, forums, webinars, seminars participation", 8),
            ("Business Development Lead",BD_KRA4, "Lead generated from Branding activities through participation, LinkedIn and Websites", 9),
            ("Business Development Lead",BD_KRA4, "Weekly 01 Post on LinkedIn", 10),
            ("Business Development Lead",BD_KRA4, "15 days 01 Blog on LinkedIn", 11),
            # Presales Lead (Excel Section 3 — Gangadhara)
            ("Presales Lead",BD_KRA1, "New opportunities, newsletters, new trends, market updates", 1),
            ("Presales Lead",BD_KRA1, "Identify prospects; email campaign", 2),
            ("Presales Lead",BD_KRA2, "Qualified sales opportunities created", 3),
            ("Presales Lead",BD_KRA2, "Lead to deal conversion", 4),
            ("Presales Lead",BD_KRA3, "Proposal to closure conversion rate", 5),
            ("Presales Lead",BD_KRA3, "No of New Strategic Partnership Signed", 6),
            ("Presales Lead",BD_KRA3, "RFP / RFQ opportunities identified/ Participation", 7),
            ("Presales Lead",BD_KRA4, "No of Industry events, forums, webinars, seminars participation", 8),
            ("Presales Lead",BD_KRA4, "Weekly 01 Post on LinkedIn", 9),
            ("Presales Lead",BD_KRA4, "15 days 01 Blog on LinkedIn", 10),
            # Business Development Manager (Excel Section 2 — middle column)
            ("Business Development Manager","Market Research & Analysis", "New opportunities, newsletters, trends, updates", 1),
            ("Business Development Manager","Market Research & Analysis", "Identify prospects; email campaign", 2),
            ("Business Development Manager","Sales Pipeline Management", "Qualified sales opportunities created", 3),
            ("Business Development Manager","Sales Pipeline Management", "Lead to deal conversion", 4),
            ("Business Development Manager","Proposal, Negotiation & Closure", "Proposal to closure conversion rate", 5),
            ("Business Development Manager","Proposal, Negotiation & Closure", "New strategic partnerships signed", 6),
            ("Business Development Manager","Proposal, Negotiation & Closure", "RFP/RFQ opportunities identified/participated", 7),
            ("Business Development Manager","Branding & Positioning", "Industry events/forums/webinars participation", 8),
            ("Business Development Manager","Branding & Positioning", "Leads generated via branding (LinkedIn, website)", 9),
            ("Business Development Manager","Branding & Positioning", "Weekly LinkedIn post", 10),
            ("Business Development Manager","Branding & Positioning", "Bi-monthly LinkedIn blog", 11),
            ("Business Development Manager","Client Relationship Management", "Client satisfaction score (CSAT \u226580%)", 12),
            ("Business Development Manager","Client Relationship Management", "Quarterly client review meetings", 13),
            ("Business Development Manager","Revenue & Growth", "Quarterly revenue achievement", 14),
            ("Business Development Manager","Revenue & Growth", "Upsell/cross-sell deals closed", 15),
            ("Business Development Manager","Innovation & Collaboration", "New service ideas proposed", 16),
            ("Business Development Manager","Innovation & Collaboration", "Joint initiatives with delivery/quality teams", 17),
            ("Business Development Manager","Governance & Reporting", "Weekly pipeline reports submitted", 18),
            ("Business Development Manager","Governance & Reporting", "Monthly BD dashboard updates", 19),
        ]
        c.execute(insert(kpi_templates), [{"category": cat, "kra": kra, "kpi": kpi, "sort_order": so, "active": True} for cat, kra, kpi, so in tpls])

        # Seed default monthly targets from KPI.xlsx
        tpl_rows = c.execute(select(kpi_templates.c.id, kpi_templates.c.category, kpi_templates.c.kpi)).fetchall()
        tpl_map = {(r[1], r[2]): r[0] for r in tpl_rows}

        bd_targets = {
            "New opportunities, newsletters, new trends, market updates": [5, 5, 5],
            "Identify prospects; email campaign": [30, 30, 50],
            "Qualified sales opportunities created": [12, 20, 28],
            "Lead to deal conversion": [5, 5, 5],
            "Proposal to closure conversion rate": [3, 3, 3],
            "No of New Strategic Partnership Signed": [5, 5, 5],
            "RFP / RFQ opportunities identified/ Participation": [8, 12, 15],
            "No of Industry events, forums, webinars, seminars participation": [1, 1, 1],
            "Lead generated from Branding activities through participation, LinkedIn and Websites": [2, 2, 2],
            "Weekly 01 Post on LinkedIn": [4, 4, 4],
            "15 days 01 Blog on LinkedIn": [2, 2, 2],
        }
        presales_targets = {
            "New opportunities, newsletters, new trends, market updates": [5, 20, 30],
            "Identify prospects; email campaign": [50, 150, 150],
            "Qualified sales opportunities created": [3, 10, 20],
            "Lead to deal conversion": [3, 5, 10],
            "Proposal to closure conversion rate": [3, 5, 10],
            "No of New Strategic Partnership Signed": [1, 1, 1],
            "RFP / RFQ opportunities identified/ Participation": [5, 5, 5],
            "No of Industry events, forums, webinars, seminars participation": [0, 0, 0],
            "Weekly 01 Post on LinkedIn": [0, 3, 3],
            "15 days 01 Blog on LinkedIn": [0, 2, 2],
        }
        am_targets = {
            "New opportunities, newsletters, trends, updates": [5, 5, 5],
            "Identify prospects; email campaign": [30, 30, 50],
            "Qualified sales opportunities created": [12, 20, 28],
            "Lead to deal conversion": [5, 5, 5],
            "Proposal to closure conversion rate": [3, 3, 3],
            "New strategic partnerships signed": [5, 5, 5],
            "RFP/RFQ opportunities identified/participated": [8, 12, 15],
            "Industry events/forums/webinars participation": [1, 2, 2],
            "Leads generated via branding (LinkedIn, website)": [2, 2, 2],
            "Weekly LinkedIn post": [4, 4, 4],
            "Bi-monthly LinkedIn blog": [2, 2, 2],
            "Client satisfaction score (CSAT \u226580%)": [80, 80, 80],
            "Quarterly client review meetings": [2, 2, 2],
            "Quarterly revenue achievement": [100, 100, 100],
            "Upsell/cross-sell deals closed": [2, 3, 3],
            "New service ideas proposed": [1, 1, 1],
            "Joint initiatives with delivery/quality teams": [2, 2, 2],
            "Weekly pipeline reports submitted": [4, 4, 4],
            "Monthly BD dashboard updates": [1, 1, 1],
        }
        months = ["2026-09", "2026-10", "2026-11"]
        target_rows = []
        for cat, tgt_map in [("Business Development Lead",bd_targets), ("Presales Lead",presales_targets), ("Business Development Manager",am_targets)]:
            for kpi_name, vals in tgt_map.items():
                tid = tpl_map.get((cat, kpi_name))
                if tid:
                    for i, v in enumerate(vals):
                        target_rows.append({"template_id": tid, "month": months[i], "target_value": float(v)})
        if target_rows:
            c.execute(insert(kpi_targets), target_rows)
