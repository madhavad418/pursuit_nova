import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import struct
import time
import logging
import uuid
from urllib.parse import urlencode
from collections import defaultdict, deque
from contextlib import asynccontextmanager, nullcontext
from datetime import date, datetime, timedelta, timezone
from typing import Any

import jwt
import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Depends, Query, Request, Response, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, insert, update, delete, func, and_, or_, text, inspect, case
from sqlalchemy.exc import IntegrityError

# Optional OpenTelemetry export. Set OTEL_EXPORTER_OTLP_ENDPOINT in production.
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
except Exception:
    trace=Resource=TracerProvider=BatchSpanProcessor=OTLPSpanExporter=None

from app.db import (
    engine, init_db, hash_password, verify_password, normalize_name, normalize_email, domain_from_url, classify_vertical, split_verticals,
    rows, row, execute,
    roles, permissions, role_permissions, users, companies, contacts, leads, meetings, moms, actions,
    opportunities, followups, opportunity_team, targets, documents, record_shares, notifications,
    workflow_rules, master_values, audit_logs, security_logs, revoked_sessions,
    org_settings, fx_rates, field_permissions, saved_views, dashboard_preferences, microsoft_integrations,
    kpi_templates, kpi_targets, kpi_actuals, generic_actions, mom_attachments,
    partner_companies, partner_contacts, partnerships, partner_opportunities, partner_meetings,
    partner_moms, partner_mom_attachments, partner_actions, partner_followups, partner_opportunity_team,
    vendor_targets, VENDOR_REGISTRATION_STATUSES, record_people,
    rfps, rfp_documents, RFP_STATUSES, RFP_QA_STATUSES, RFP_DOCUMENT_CATEGORIES,
)

APP_NAME = "JSAN PursuitNova"
APP_VERSION = "6.0.0-FullStack"
SESSION_COOKIE = "pursuitnova_session"
CSRF_COOKIE = "pursuitnova_csrf"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-this-before-production")
SESSION_MINUTES = int(os.getenv("SESSION_MINUTES", "480"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
DEMO_PASSWORD = os.getenv("SEED_DEMO_PASSWORD", "PursuitNovaDemo@2026")
MICROSOFT_TENANT_ID=os.getenv("MICROSOFT_TENANT_ID", "common")
MICROSOFT_CLIENT_ID=os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET=os.getenv("MICROSOFT_CLIENT_SECRET", "")
MICROSOFT_REDIRECT_URI=os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/api/integrations/microsoft/callback")
MICROSOFT_SCOPES=os.getenv("MICROSOFT_SCOPES", "openid profile offline_access User.Read Mail.Send Calendars.ReadWrite OnlineMeetings.ReadWrite")
INTEGRATION_ENCRYPTION_KEY=os.getenv("INTEGRATION_ENCRYPTION_KEY", "")
METRICS_TOKEN=os.getenv("METRICS_TOKEN", "")
OTEL_EXPORTER_OTLP_ENDPOINT=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
# Only this login may retrieve (preview or download) uploaded RFP documents; every other user can see
# that a document exists but cannot pull its bytes. Configurable for hand-over without a code change.
RFP_DOWNLOAD_EMAIL=os.getenv("RFP_DOWNLOAD_EMAIL", "rreddy@jsanconsulting.com").strip().lower()
RFP_DOCUMENTS_PER_RFP=10

@asynccontextmanager
async def lifespan(app):
    env=os.getenv("APP_ENV","development").lower()
    if env=="production":
        if JWT_SECRET.startswith("dev-only") or len(JWT_SECRET)<32: raise RuntimeError("Production requires a strong JWT_SECRET (32+ chars)")
        if not COOKIE_SECURE: raise RuntimeError("Production requires COOKIE_SECURE=true")
        if os.getenv("SEED_DEMO","false").lower()=="true": raise RuntimeError("Production cannot run with SEED_DEMO=true")
        if os.getenv("SEED_DEMO_DATA","false").lower()=="true": raise RuntimeError("Production cannot run with SEED_DEMO_DATA=true")
        if MICROSOFT_CLIENT_ID and not INTEGRATION_ENCRYPTION_KEY: raise RuntimeError("Production Microsoft integration requires INTEGRATION_ENCRYPTION_KEY")
    # With AUTO_CREATE_SCHEMA=false Alembic owns the schema (see Dockerfile); reference data is still ensured on every start.
    init_db(create_schema=os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true")
    global _HAS_CATEGORY
    _HAS_CATEGORY = _user_has_category()
    yield

app = FastAPI(title=f"{APP_NAME} API", version=APP_VERSION, lifespan=lifespan)
if OTEL_EXPORTER_OTLP_ENDPOINT and TracerProvider:
    provider=TracerProvider(resource=Resource.create({"service.name":"jsan-pursuitnova","service.version":APP_VERSION}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")+"/v1/traces")))
    trace.set_tracer_provider(provider)
TRACER=trace.get_tracer("jsan-pursuitnova") if trace else None
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def request_observability(request:Request, call_next):
    rid=request.headers.get("x-request-id") or str(uuid.uuid4()); start=time.perf_counter(); REQUEST_METRICS["requests"]+=1
    span_cm=TRACER.start_as_current_span(f"{request.method} {request.url.path}") if TRACER else nullcontext()
    try:
        with span_cm as span:
            if span:
                span.set_attribute("http.request.method",request.method); span.set_attribute("url.path",request.url.path); span.set_attribute("request.id",rid)
            response=await call_next(request)
            if span: span.set_attribute("http.response.status_code",response.status_code)
    except Exception:
        REQUEST_METRICS["errors"]+=1; json_log("request_error",request_id=rid,path=request.url.path,method=request.method); raise
    elapsed=(time.perf_counter()-start)*1000; REQUEST_METRICS["latency_ms_total"]+=elapsed
    if response.status_code>=500: REQUEST_METRICS["errors"]+=1
    response.headers["X-Request-ID"]=rid
    response.headers.setdefault("X-Content-Type-Options","nosniff")
    response.headers.setdefault("X-Frame-Options","DENY")
    response.headers.setdefault("Referrer-Policy","strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy","camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy","default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if COOKIE_SECURE: response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
    # Caching: hashed build files never change, but the page that references them must be rechecked on every
    # load, otherwise a browser keeps an old index.html pointing at files a newer deploy removed (blank page).
    path=request.url.path
    if path.startswith("/api/"): response.headers.setdefault("Cache-Control","no-store")
    elif path.startswith("/assets/") and response.status_code==200: response.headers.setdefault("Cache-Control","public, max-age=31536000, immutable")
    elif response.headers.get("content-type","").startswith("text/html") or path in ("/","/index.html","/sw.js","/manifest.webmanifest"): response.headers.setdefault("Cache-Control","no-cache")
    json_log("request",request_id=rid,path=request.url.path,method=request.method,status=response.status_code,latency_ms=round(elapsed,2))
    return response

class Login(BaseModel):
    email: str
    password: str
    otp: str | None = None

class Payload(BaseModel):
    data: dict[str, Any]

LOGIN_ATTEMPTS: dict[str, deque] = defaultdict(deque)
REQUEST_METRICS={"requests":0,"errors":0,"latency_ms_total":0.0,"started_at":time.time()}
logger=logging.getLogger("pursuitnova")
if not logger.handlers:
    h=logging.StreamHandler(); h.setFormatter(logging.Formatter('%(message)s')); logger.addHandler(h); logger.setLevel(logging.INFO)
MS_OAUTH_STATE: dict[str, tuple[int,float]] = {}

def json_log(event, **kwargs):
    logger.info(json.dumps({"ts":utcnow().isoformat(),"event":event,**kwargs},default=str))

def utcnow(): return datetime.now(timezone.utc)
def iso_utc(value):
    """Timestamps are stored as UTC without a zone; send them with an explicit Z so browsers show local time correctly."""
    if not value: return None
    if isinstance(value, str):
        try: value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
    if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
def today_str(): return date.today().isoformat()
def asdict(r): return dict(r._mapping) if r is not None else None

def audit(user_id, entity_type, entity_id, action, details=None):
    execute(insert(audit_logs).values(user_id=user_id, entity_type=entity_type, entity_id=entity_id, action=action, details=json.dumps(details or {}, default=str)))

def security_log(user_id, event_type, success, request: Request | None = None, details=None):
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent") if request else None
    execute(insert(security_logs).values(user_id=user_id, event_type=event_type, success=success, ip_address=ip, user_agent=ua, details=json.dumps(details or {}, default=str)))

def make_token(user_id: int):
    jti = secrets.token_urlsafe(24)
    exp = utcnow() + timedelta(minutes=SESSION_MINUTES)
    token = jwt.encode({"sub": str(user_id), "jti": jti, "exp": exp}, JWT_SECRET, algorithm="HS256")
    return token, jti, exp

def get_permissions(user_id: int) -> list[str]:
    stmt = (select(permissions.c.code)
            .select_from(users.join(role_permissions, users.c.role_id == role_permissions.c.role_id)
                         .join(permissions, permissions.c.id == role_permissions.c.permission_id))
            .where(users.c.id == user_id))
    return [r["code"] for r in rows(stmt)]

# KPI categories were renamed. Rows saved under the old names stay untouched in the database;
# they are read as the new names, and everything written from now on uses the new names.
KPI_CATEGORIES = ("Business Development Manager", "Business Development Lead", "Presales Lead")
LEGACY_CATEGORY = {"Account Management": "Business Development Manager", "Business Development": "Business Development Lead", "Presales": "Presales Lead"}

def canon_category(value):
    if not value: return value
    v = str(value).strip()
    return LEGACY_CATEGORY.get(v, v)

def category_names(value):
    """Every stored spelling of a category: the current name plus any legacy name mapping to it."""
    c = canon_category(value)
    return [c] + [old for old, new in LEGACY_CATEGORY.items() if new == c]

def _user_has_category():
    try:
        return "category" in {c["name"] for c in inspect(engine).get_columns("users")}
    except Exception:
        return False

_HAS_CATEGORY = None
def safe_user(user_id: int):
    global _HAS_CATEGORY
    if _HAS_CATEGORY is None:
        _HAS_CATEGORY = _user_has_category()
    cols = [users.c.id, users.c.name, users.c.email, users.c.manager_id, users.c.title, users.c.region,
            users.c.active, users.c.mfa_enabled, roles.c.name.label("role"), roles.c.scope_type, roles.c.rank]
    if _HAS_CATEGORY:
        cols.insert(6, users.c.category)
    r = row(select(*cols).select_from(users.join(roles, users.c.role_id == roles.c.id)).where(users.c.id == user_id))
    if r:
        r["permissions"] = get_permissions(user_id)
        r["category"] = canon_category(r.get("category"))
    return r

def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Authentication required")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        uid = int(payload["sub"]); jti = payload["jti"]
    except Exception:
        raise HTTPException(401, "Invalid or expired session")
    if row(select(revoked_sessions.c.jti).where(revoked_sessions.c.jti == jti)):
        raise HTTPException(401, "Session revoked")
    u = safe_user(uid)
    if not u or not u["active"]:
        raise HTTPException(401, "User unavailable")
    u["jti"] = jti
    return u

def require_csrf(request: Request, u=Depends(current_user)):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        cookie = request.cookies.get(CSRF_COOKIE)
        header = request.headers.get("x-csrf-token")
        if not cookie or not header or not hmac.compare_digest(cookie, header):
            raise HTTPException(403, "CSRF validation failed")
    return u

def require_perm(code: str):
    def dep(u=Depends(current_user)):
        if code not in u.get("permissions", []):
            raise HTTPException(403, f"Permission required: {code}")
        return u
    return dep

def org_setting(key:str, default=None):
    r=row(select(org_settings.c.value).where(org_settings.c.key==key)); return r["value"] if r else default

def field_access(u, entity_type:str, field_name:str):
    r=row(select(field_permissions.c.can_view,field_permissions.c.can_edit).where(and_(field_permissions.c.role_id==row(select(users.c.role_id).where(users.c.id==u["id"]))["role_id"],field_permissions.c.entity_type==entity_type,field_permissions.c.field_name==field_name)))
    return (bool(r["can_view"]),bool(r["can_edit"])) if r else (True,True)

def mask_fields(u, entity_type:str, record:dict):
    if not record: return record
    out=dict(record)
    for f in list(out):
        view,_=field_access(u,entity_type,f)
        if not view: out[f]=None
    return out

def ensure_fields_editable(u, entity_type:str, data:dict):
    denied=[]
    for f in data:
        _,edit=field_access(u,entity_type,f)
        if not edit: denied.append(f)
    if denied: raise HTTPException(403,"Field edit permission denied: "+", ".join(denied))

def corporate_currency(): return org_setting("corporate_currency","USD")

def fx_map():
    return {r["currency"]:float(r["rate_to_corporate"]) for r in rows(select(fx_rates))}

def to_corporate(amount, currency, rates=None):
    rates=rates or fx_map(); cur=(currency or corporate_currency()).upper(); rate=rates.get(cur)
    if rate is None: return None
    return float(amount or 0)*rate

def fernet():
    key=INTEGRATION_ENCRYPTION_KEY.strip()
    if not key:
        digest=hashlib.sha256(JWT_SECRET.encode()).digest(); key=base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())

def enc_token(value:str): return fernet().encrypt(value.encode()).decode()
def dec_token(value:str):
    try: return fernet().decrypt(value.encode()).decode()
    except InvalidToken: raise HTTPException(500,"Integration token encryption key mismatch")

def descendants(user_id: int, include_inactive: bool=False) -> list[int]:
    result=[]; frontier=[user_id]
    while frontier:
        cond=users.c.manager_id.in_(frontier) if include_inactive else and_(users.c.manager_id.in_(frontier), users.c.active == True)
        found=[r["id"] for r in rows(select(users.c.id).where(cond))]
        result.extend(found); frontier=found
    return result

def is_super(u) -> bool:
    """Only organisation-wide roles (Super Admin) see and manage everything."""
    return u.get("scope_type") == "all"

def org_root(user_id: int) -> int:
    """The top of a user's reporting chain below the organisation-wide layer, i.e. the Admin whose organisation they belong to."""
    cursor=user_id; seen=set()
    while cursor not in seen:
        seen.add(cursor)
        r=row(select(users.c.manager_id).where(users.c.id==cursor)); manager_id=r.get("manager_id") if r else None
        if not manager_id: return cursor
        m=row(select(roles.c.scope_type).select_from(users.join(roles,users.c.role_id==roles.c.id)).where(users.c.id==manager_id))
        if m and m["scope_type"]=="all": return cursor
        cursor=manager_id
    return cursor

def scope_user_ids(u) -> list[int]:
    if u["scope_type"] == "all":
        return [r["id"] for r in rows(select(users.c.id).where(users.c.active == True))]
    if u["scope_type"] == "team":
        return [u["id"]] + descendants(u["id"])
    return [u["id"]]

def can_assign(u, target_id: int) -> bool:
    target = safe_user(target_id)
    if not target or not target["active"]: return False
    if is_super(u): return True
    if target["role"] == "Presales Lead" and org_root(target_id) == org_root(u["id"]): return True
    return target_id in scope_user_ids(u)

# ── Extra people on a prospect ("co-owners") or an action ("co-assignees") ──
# The primary owner_id / assigned_to columns keep working exactly as before; these are additional people stored in
# record_people. Only Admin and Super Admin can change them.
def is_admin_role(u) -> bool:
    return u["role"] in ("Super Admin","Admin")

def people_map(entity_type, ids=None):
    """{entity_id: [{"id","name"}, ...]} of the extra people, in the order they were added."""
    stmt=select(record_people.c.entity_id,record_people.c.user_id,users.c.name).select_from(record_people.join(users,users.c.id==record_people.c.user_id)).where(record_people.c.entity_type==entity_type).order_by(record_people.c.id)
    if ids is not None:
        ids=list(ids)
        if not ids: return {}
        if len(ids)<=500: stmt=stmt.where(record_people.c.entity_id.in_(ids))
    out={}
    for r in rows(stmt): out.setdefault(r["entity_id"],[]).append({"id":r["user_id"],"name":r["name"]})
    return out

def attach_people(items, entity_type, key):
    pm=people_map(entity_type,[i["id"] for i in items]) if items else {}
    for i in items: i[key]=pm.get(i["id"],[])
    return items

def extra_person_ids(entity_type, entity_id) -> list[int]:
    return [r["user_id"] for r in rows(select(record_people.c.user_id).where(and_(record_people.c.entity_type==entity_type,record_people.c.entity_id==entity_id)).order_by(record_people.c.id))]

def parse_person_ids(v, label) -> list[int]:
    if v is None: return []
    if not isinstance(v,list): raise HTTPException(400,f"{label} must be a list of users")
    out=[]
    for x in v:
        try: i=int(x)
        except (TypeError,ValueError): raise HTTPException(400,f"{label} contains an invalid user")
        if i not in out: out.append(i)
    return out

def plan_people(u, entity_type, entity_id, primary_id, wanted, label):
    """Work out who to add/remove so the extras equal `wanted` (minus the primary). Validates everything and writes nothing,
    so a failing request never leaves a half-applied change. Returns (added, removed)."""
    wanted=[i for i in wanted if i!=primary_id]
    current=extra_person_ids(entity_type,entity_id) if entity_id else []
    added=[i for i in wanted if i not in current]; removed=[i for i in current if i not in wanted]
    if not added and not removed: return [],[]
    if not is_admin_role(u): raise HTTPException(403,f"Only an Admin or Super Admin can change the additional {label}")
    for i in added:
        if not can_assign(u,i): raise HTTPException(403,f"You cannot add that person to the additional {label}")
    return added,removed

def apply_people(u, entity_type, entity_id, added, removed):
    with engine.begin() as c:
        if removed: c.execute(delete(record_people).where(and_(record_people.c.entity_type==entity_type,record_people.c.entity_id==entity_id,record_people.c.user_id.in_(removed))))
        for i in added: c.execute(insert(record_people).values(entity_type=entity_type,entity_id=entity_id,user_id=i,created_by=u["id"]))

def drop_person(entity_type, entity_id, user_id):
    """A person promoted to primary must not stay listed as an extra as well."""
    execute(delete(record_people).where(and_(record_people.c.entity_type==entity_type,record_people.c.entity_id==entity_id,record_people.c.user_id==user_id)))

def clear_people(entity_type, entity_ids):
    entity_ids=list(entity_ids)
    if entity_ids: execute(delete(record_people).where(and_(record_people.c.entity_type==entity_type,record_people.c.entity_id.in_(entity_ids))))

def is_assignee(a, user_id) -> bool:
    return a["assigned_to"]==user_id or any(p["id"]==user_id for p in a.get("co_assignees") or [])

def notify_assigned(user_ids, title, message, entity_type, entity_id, due_date):
    for uid in user_ids:
        execute(insert(notifications).values(user_id=uid,notification_type="Action Assigned",title=title,message=message,entity_type=entity_type,entity_id=entity_id,due_date=due_date,severity="info"))

def has_share(entity_type, entity_id, user_id, edit=False):
    stmt=select(record_shares.c.id, record_shares.c.access_level).where(and_(record_shares.c.entity_type==entity_type, record_shares.c.entity_id==entity_id, record_shares.c.user_id==user_id))
    r=row(stmt)
    return bool(r and (not edit or r["access_level"]=="edit"))

def lead_owner_ids(lead_id: int) -> list[int]:
    """Primary owner first, then any co-owners."""
    l=row(select(leads.c.owner_id).where(leads.c.id==lead_id))
    return [l["owner_id"]]+extra_person_ids("lead",lead_id) if l else []

def can_view_lead(u, lead_id: int) -> bool:
    owners=lead_owner_ids(lead_id)
    if not owners: return False
    if set(owners)&set(scope_user_ids(u)) or has_share("lead", lead_id, u["id"]): return True
    if u["role"] == "Presales Lead":
        if row(select(actions.c.id).where(and_(actions.c.lead_id==lead_id, actions.c.assigned_to==u["id"])).limit(1)): return True
        if row(select(record_people.c.id).select_from(record_people.join(actions,actions.c.id==record_people.c.entity_id)).where(and_(record_people.c.entity_type=="action",record_people.c.user_id==u["id"],actions.c.lead_id==lead_id)).limit(1)): return True
        if row(select(opportunity_team.c.opportunity_id).select_from(opportunity_team.join(opportunities, opportunities.c.id==opportunity_team.c.opportunity_id)).where(and_(opportunities.c.lead_id==lead_id, opportunity_team.c.user_id==u["id"])).limit(1)): return True
    return False

def can_edit_lead(u, lead_id: int) -> bool:
    if "LEAD_EDIT" not in u["permissions"]: return False
    owners=lead_owner_ids(lead_id)
    return bool(owners and (set(owners)&set(scope_user_ids(u)) or has_share("lead", lead_id, u["id"], True)))

def can_view_opp(u, opp_id: int) -> bool:
    o=row(select(opportunities.c.owner_id, opportunities.c.presales_owner_id).where(opportunities.c.id==opp_id))
    if not o: return False
    if o["owner_id"] in scope_user_ids(u) or o.get("presales_owner_id")==u["id"] or has_share("opportunity", opp_id, u["id"]): return True
    return bool(row(select(opportunity_team.c.opportunity_id).where(and_(opportunity_team.c.opportunity_id==opp_id, opportunity_team.c.user_id==u["id"]))))

def can_edit_opp(u, opp_id: int) -> bool:
    return "OPPORTUNITY_EDIT" in u["permissions"] and can_view_opp(u, opp_id)

def _clean_text(v, max_len=None):
    if v is None: return None
    t=str(v).strip()
    if max_len and len(t)>max_len: raise HTTPException(400,f"Value is too long (max {max_len} characters)")
    return t or None

def _clean_url(v, label):
    t=_clean_text(v, 500)
    if not t: return None
    if not t.lower().startswith(("http://","https://")): t="https://"+t
    if " " in t or "." not in t.split("//",1)[1]: raise HTTPException(400,f"{label} does not look like a valid link")
    return t

LEAD_STATUSES=("New","Assigned","Contacted","Engaged","Qualified","Converted","On Hold","Unresponsive","Disqualified","Lost")
LEAD_TEMPERATURES=("Hot","Warm","Cold")

def can_access_company_relationship(u, company_id: int) -> bool:
    """Company identity is globally searchable; relationship PII is scoped to owned/shared work."""
    if u.get("scope_type") == "all": return True
    for lr in rows(select(leads.c.id).where(leads.c.company_id==company_id)):
        if can_view_lead(u, lr["id"]): return True
    for op in rows(select(opportunities.c.id).where(opportunities.c.company_id==company_id)):
        if can_view_opp(u, op["id"]): return True
    return False

def verify_totp(secret: str, code: str, window: int=1) -> bool:
    try:
        key=base64.b32decode(secret.upper() + "="*((8-len(secret)%8)%8))
        now=int(time.time())//30
        for offset in range(-window, window+1):
            msg=struct.pack(">Q", now+offset)
            digest=hmac.new(key,msg,hashlib.sha1).digest(); pos=digest[-1]&0x0f
            n=(struct.unpack(">I",digest[pos:pos+4])[0]&0x7fffffff)%1000000
            if hmac.compare_digest(f"{n:06d}", str(code).zfill(6)): return True
    except Exception: pass
    return False

def make_totp_secret(): return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def issue_session(response: Response, uid: int):
    token,jti,exp=make_token(uid); csrf=secrets.token_urlsafe(32)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=SESSION_MINUTES*60, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=COOKIE_SECURE, samesite=COOKIE_SAMESITE, max_age=SESSION_MINUTES*60, path="/")
    return csrf

def q_current(): return f"Q{((date.today().month-1)//3)+1}"
def forecast_from_status(status):
    if status.startswith("Closed "): return "Closed"
    if status == "Negotiation": return "Commit"
    if status in {"Proposal Submitted","Awaiting Response"}: return "Best Case"
    return "Pipeline"

def validate_outcome(status, d):
    if status=="Closed Won" and float(d.get("final_amount") or d.get("amount") or 0)<=0: raise HTTPException(400,"Final deal amount is required for Closed Won")
    if status=="Closed Lost" and not d.get("lost_reason"): raise HTTPException(400,"Lost reason is required for Closed Lost")
    if status=="Closed Hold" and (not d.get("hold_reason") or not d.get("hold_review_date")): raise HTTPException(400,"Hold reason and review date are required for Closed Hold")

def user_name(uid):
    r=row(select(users.c.name).where(users.c.id==uid)); return r["name"] if r else "Unknown"

def opportunity_rows(u):
    uo=users.alias("uo"); up=users.alias("up")
    stmt=select(opportunities, companies.c.name.label("company_name"), companies.c.vertical, uo.c.name.label("owner_name"), up.c.name.label("presales_owner_name"), leads.c.temperature).select_from(
        opportunities.join(companies, companies.c.id==opportunities.c.company_id).join(leads, leads.c.id==opportunities.c.lead_id).join(uo, uo.c.id==opportunities.c.owner_id).outerjoin(up, up.c.id==opportunities.c.presales_owner_id)
    )
    base=rows(stmt.order_by(opportunities.c.updated_at.desc()))
    out=[]
    for x in base:
        if can_view_opp(u,x["id"]):
            try: x["age_days"]=(date.today()-x["created_at"].date()).days
            except Exception: x["age_days"]=0
            out.append(mask_fields(u,"opportunity",x))
    return out

def lead_rows(u):
    owner=users.alias("owner")
    stmt=select(leads, companies.c.name.label("company_name"), companies.c.vertical, companies.c.website, companies.c.linkedin_url, companies.c.external_url, owner.c.name.label("owner_name")).select_from(
        leads.join(companies, companies.c.id==leads.c.company_id).join(owner, owner.c.id==leads.c.owner_id)
    ).order_by(leads.c.updated_at.desc())
    base=rows(stmt); out=[]; co=people_map("lead")
    for x in base:
        if can_view_lead(u,x["id"]):
            x["co_owners"]=co.get(x["id"],[])
            ct=row(select(contacts.c.name).where(contacts.c.company_id==x["company_id"]).order_by(contacts.c.is_primary.desc(),contacts.c.id).limit(1))
            x["primary_contact"]=ct["name"] if ct else None
            ac=row(select(func.count()).select_from(actions).where(and_(actions.c.lead_id==x["id"], actions.c.status.not_in(["Completed","Cancelled"]))))
            x["open_actions"]=list(ac.values())[0] if ac else 0
            x["last_activity"]=(x["updated_at"].date().isoformat() if x.get("updated_at") else None)
            out.append(x)
    temporder={"Hot":0,"Warm":1,"Cold":2}; out.sort(key=lambda x:(temporder.get(x["temperature"],9), str(x.get("updated_at"))), reverse=False)
    return out

@app.get("/api/health")
def health():
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"status":"ok","name":APP_NAME,"version":APP_VERSION,"database":engine.dialect.name}

@app.post("/api/auth/login")
def login(p: Login, request: Request, response: Response):
    key=(request.client.host if request.client else "unknown")+":"+p.email.lower()
    now=time.time(); dq=LOGIN_ATTEMPTS[key]
    while dq and now-dq[0]>600: dq.popleft()
    if len(dq)>=8:
        security_log(None,"LOGIN_THROTTLED",False,request,{"email":p.email}); raise HTTPException(429,"Too many login attempts. Try again later.")
    rr=row(select(users.c.id,users.c.password_hash,users.c.active,users.c.mfa_enabled,users.c.mfa_secret).where(func.lower(users.c.email)==p.email.lower()))
    if not rr or not rr["active"] or not verify_password(p.password,rr["password_hash"]):
        dq.append(now); security_log(rr["id"] if rr else None,"LOGIN_FAILED",False,request,{"email":p.email}); raise HTTPException(401,"Invalid credentials")
    if rr["mfa_enabled"]:
        if not p.otp: return {"mfa_required":True,"message":"Enter the 6-digit authenticator code."}
        if not verify_totp(rr["mfa_secret"],p.otp): dq.append(now); security_log(rr["id"],"MFA_FAILED",False,request); raise HTTPException(401,"Invalid authenticator code")
    dq.clear(); execute(update(users).where(users.c.id==rr["id"]).values(last_login_at=utcnow(),updated_at=utcnow()))
    csrf=issue_session(response,rr["id"]); security_log(rr["id"],"LOGIN_SUCCESS",True,request)
    return {"user":safe_user(rr["id"]),"csrf_token":csrf}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response, u=Depends(require_csrf)):
    token=request.cookies.get(SESSION_COOKIE)
    try:
        p=jwt.decode(token,JWT_SECRET,algorithms=["HS256"]); exp=datetime.fromtimestamp(p["exp"],tz=timezone.utc)
        execute(insert(revoked_sessions).values(jti=p["jti"],user_id=u["id"],expires_at=exp))
    except Exception: pass
    response.delete_cookie(SESSION_COOKIE,path="/"); response.delete_cookie(CSRF_COOKIE,path="/")
    security_log(u["id"],"LOGOUT",True,request); return {"ok":True}

@app.get("/api/auth/me")
def me(u=Depends(current_user)): return u

MIN_PASSWORD_LENGTH=8

@app.post("/api/auth/change-password")
def change_password(p:Payload,request:Request,u=Depends(require_csrf)):
    d=p.data; current=str(d.get("current_password") or ""); new=str(d.get("new_password") or "")
    rr=row(select(users.c.password_hash).where(users.c.id==u["id"]))
    if not rr or not verify_password(current,rr["password_hash"]):
        security_log(u["id"],"PASSWORD_CHANGE_FAILED",False,request); raise HTTPException(400,"Current password is incorrect")
    if len(new)<MIN_PASSWORD_LENGTH: raise HTTPException(400,f"New password must be at least {MIN_PASSWORD_LENGTH} characters")
    if new==current: raise HTTPException(400,"New password must be different from the current one")
    execute(update(users).where(users.c.id==u["id"]).values(password_hash=hash_password(new),updated_at=utcnow()))
    security_log(u["id"],"PASSWORD_CHANGED",True,request); audit(u["id"],"user",u["id"],"PASSWORD_CHANGE"); return {"ok":True}

@app.get("/api/auth/csrf")
def csrf(request:Request,response:Response,u=Depends(current_user)):
    token=request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
    if not request.cookies.get(CSRF_COOKIE): response.set_cookie(CSRF_COOKIE,token,httponly=False,secure=COOKIE_SECURE,samesite=COOKIE_SAMESITE,max_age=SESSION_MINUTES*60,path="/")
    return {"csrf_token":token}

@app.post("/api/auth/mfa/setup")
def mfa_setup(u=Depends(require_csrf)):
    secret=make_totp_secret(); execute(update(users).where(users.c.id==u["id"]).values(mfa_secret=secret,mfa_enabled=False,updated_at=utcnow()))
    issuer="JSAN-PursuitNova"; account=u["email"]
    return {"secret":secret,"otpauth_url":f"otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits=6&period=30"}

@app.post("/api/auth/mfa/enable")
def mfa_enable(p:Payload,u=Depends(require_csrf)):
    rr=row(select(users.c.mfa_secret).where(users.c.id==u["id"])); code=str(p.data.get("code") or "")
    if not rr or not rr["mfa_secret"] or not verify_totp(rr["mfa_secret"],code): raise HTTPException(400,"Invalid authenticator code")
    execute(update(users).where(users.c.id==u["id"]).values(mfa_enabled=True,updated_at=utcnow())); audit(u["id"],"user",u["id"],"MFA_ENABLED"); return {"enabled":True}

@app.get("/api/users/assignable")
def assignable(u=Depends(current_user)):
    ids=set(scope_user_ids(u)); root=None if is_super(u) else org_root(u["id"])
    ids.update(r["id"] for r in rows(select(users.c.id).select_from(users.join(roles,users.c.role_id==roles.c.id)).where(and_(roles.c.name=="Presales Lead",users.c.active==True))) if root is None or org_root(r["id"])==root)
    cols=[users.c.id,users.c.name,users.c.email,roles.c.name.label("role"),users.c.manager_id,users.c.title,users.c.region]
    if _HAS_CATEGORY: cols.append(users.c.category)
    stmt=select(*cols).select_from(users.join(roles,users.c.role_id==roles.c.id)).where(and_(users.c.active==True,users.c.id.in_(sorted(ids)))).order_by(roles.c.rank,users.c.name)
    return [{**r,"category":canon_category(r.get("category"))} for r in rows(stmt)]

@app.get("/api/users")
def list_users(u=Depends(require_perm("USER_ADMIN"))):
    m=users.alias("m")
    cols=[users.c.id,users.c.name,users.c.email,roles.c.name.label("role"),users.c.manager_id,m.c.name.label("manager_name"),users.c.title,users.c.region]
    if _HAS_CATEGORY: cols.append(users.c.category)
    cols+=[users.c.active,users.c.mfa_enabled,users.c.created_at]
    out=rows(select(*cols).select_from(users.join(roles,users.c.role_id==roles.c.id).outerjoin(m,m.c.id==users.c.manager_id)).where(users.c.id.in_(sorted(managed_user_ids(u)|{u["id"]}))).order_by(users.c.id))
    for r in out: r["category"]=canon_category(r.get("category"))
    return out

def managed_user_ids(u) -> set[int]:
    """Users an administrator may manage: everyone for organisation-wide roles, otherwise their own reporting tree."""
    if is_super(u): return {r["id"] for r in rows(select(users.c.id))}
    return set(descendants(u["id"], include_inactive=True))

def ensure_manager_in_hierarchy(u, manager_id:int|None):
    if is_super(u): return
    if not manager_id or (manager_id!=u["id"] and manager_id not in managed_user_ids(u)):
        raise HTTPException(403,"Reporting manager must be you or someone in your hierarchy")

def validate_manager_assignment(user_id:int|None, manager_id:int|None):
    if not manager_id: return
    if user_id and manager_id==user_id: raise HTTPException(400,"A user cannot report to themselves")
    if not row(select(users.c.id).where(and_(users.c.id==manager_id,users.c.active==True))): raise HTTPException(400,"Reporting manager not found")
    if user_id:
        cursor=manager_id; seen=set()
        while cursor and cursor not in seen:
            if cursor==user_id: raise HTTPException(400,"Reporting hierarchy cycle is not allowed")
            seen.add(cursor); r=row(select(users.c.manager_id).where(users.c.id==cursor)); cursor=r.get("manager_id") if r else None

@app.post("/api/users")
def create_user(p:Payload,u=Depends(require_csrf)):
    if "USER_ADMIN" not in u["permissions"]: raise HTTPException(403,"User administration permission required")
    d=p.data; rr=row(select(roles).where(roles.c.name==d.get("role")))
    if not rr or not all(d.get(k) for k in ("name","email","password")): raise HTTPException(400,"Name, email, role and temporary password are required")
    if not role_assignable(u,rr): raise HTTPException(403,f"You cannot assign the {rr['name']} role")
    if len(str(d["password"]))<MIN_PASSWORD_LENGTH: raise HTTPException(400,f"Temporary password must be at least {MIN_PASSWORD_LENGTH} characters")
    manager_id=int(d["manager_id"]) if d.get("manager_id") else (None if is_super(u) else u["id"])
    ensure_manager_in_hierarchy(u,manager_id)
    validate_manager_assignment(None,manager_id)
    uvals=dict(name=d["name"],email=d["email"].lower(),password_hash=hash_password(d["password"]),role_id=rr["id"],manager_id=manager_id,title=d.get("title"),region=d.get("region"),active=True)
    if _HAS_CATEGORY and d.get("category"): uvals["category"]=canon_category(d["category"])
    try: uid=execute(insert(users).values(**uvals))
    except IntegrityError: raise HTTPException(400,"Email already exists")
    audit(u["id"],"user",uid,"CREATE",{"name":d["name"],"role":d["role"]}); return safe_user(uid)

@app.put("/api/users/{user_id}")
def update_user(user_id:int,p:Payload,u=Depends(require_csrf)):
    if "USER_ADMIN" not in u["permissions"]: raise HTTPException(403,"User administration permission required")
    if not is_super(u) and user_id not in managed_user_ids(u): raise HTTPException(403,"You can only manage users in your own hierarchy")
    d=p.data; vals={}
    for k in (("name","email","manager_id","title","region","category","active") if _HAS_CATEGORY else ("name","email","manager_id","title","region","active")):
        if k in d: vals[k]=d[k] if d[k]!="" else None
    if "email" in vals and vals["email"]: vals["email"]=vals["email"].strip().lower()
    if vals.get("category"): vals["category"]=canon_category(vals["category"])
    if d.get("role"):
        rr=row(select(roles).where(roles.c.name==d["role"]))
        if not rr: raise HTTPException(400,"Invalid role")
        if not role_assignable(u,rr): raise HTTPException(403,f"You cannot assign the {rr['name']} role")
        vals["role_id"]=rr["id"]
    if d.get("password"):
        if len(str(d["password"]))<MIN_PASSWORD_LENGTH: raise HTTPException(400,f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
        vals["password_hash"]=hash_password(d["password"])
    if "manager_id" in vals:
        manager_id=int(vals["manager_id"]) if vals["manager_id"] else None
        ensure_manager_in_hierarchy(u,manager_id); validate_manager_assignment(user_id,manager_id)
    vals["updated_at"]=utcnow(); execute(update(users).where(users.c.id==user_id).values(**vals)); audit(u["id"],"user",user_id,"UPDATE",{k:v for k,v in d.items() if k!="password"}); return safe_user(user_id)

ROLE_SCOPES=("all","team","self","assigned")

def role_owners(u) -> set[int]:
    return managed_user_ids(u)|{u["id"]}

def role_visible(u, r, owners=None) -> bool:
    """Built-in and Super Admin roles are shared; a role an Admin creates belongs to that Admin's organisation."""
    if is_super(u) or r.get("created_by") is None: return True
    return r["created_by"] in (owners if owners is not None else role_owners(u))

def role_assignable(u, r, owners=None) -> bool:
    """Admins may only hand out roles visible to them that rank below their own and are not organisation-wide."""
    if is_super(u): return True
    return role_visible(u,r,owners) and r["scope_type"]!="all" and int(r["rank"])>int(u["rank"])

def role_editable(u, r, owners=None) -> bool:
    """Admins shape only roles their own organisation created; shared roles are changed by Super Admins."""
    if r.get("name")==u["role"]: return False
    if is_super(u): return True
    return r.get("created_by") is not None and role_assignable(u,r,owners)

def editable_role(u, role_id:int):
    if "ROLE_ADMIN" not in u["permissions"]: raise HTTPException(403,"Role administration permission required")
    r=row(select(roles).where(roles.c.id==role_id))
    if not r or not role_visible(u,r): raise HTTPException(404,"Role not found")
    if not role_editable(u,r): raise HTTPException(403,"You cannot modify this role")
    return r

def ensure_grantable(u, codes):
    if is_super(u): return
    extra=sorted(set(codes)-set(u["permissions"]))
    if extra: raise HTTPException(403,"You cannot grant permissions you do not hold: "+", ".join(extra))

def set_role_permissions(role_id:int, codes):
    permrows=rows(select(permissions.c.id,permissions.c.code).where(permissions.c.code.in_(codes))) if codes else []
    with engine.begin() as c:
        c.execute(delete(role_permissions).where(role_permissions.c.role_id==role_id))
        if permrows: c.execute(insert(role_permissions),[{"role_id":role_id,"permission_id":x["id"]} for x in permrows])

@app.get("/api/admin/roles")
def role_matrix(u=Depends(require_perm("ROLE_ADMIN"))):
    owners=role_owners(u); out=[]
    for r in rows(select(roles).order_by(roles.c.rank,roles.c.name)):
        if not role_visible(u,r,owners): continue
        codes=[x["code"] for x in rows(select(permissions.c.code).select_from(role_permissions.join(permissions,permissions.c.id==role_permissions.c.permission_id)).where(role_permissions.c.role_id==r["id"]).order_by(permissions.c.code))]
        counted=select(func.count().label("n")).select_from(users).where(users.c.role_id==r["id"])
        if not is_super(u): counted=counted.where(users.c.id.in_(owners))
        out.append({**r,"permissions":codes,"user_count":row(counted)["n"],"assignable":role_assignable(u,r,owners),"editable":role_editable(u,r,owners)})
    catalog=rows(select(permissions).order_by(permissions.c.code))
    return {"roles":out,"permission_catalog":catalog,"grantable":[x["code"] for x in catalog] if is_super(u) else sorted(u["permissions"]),
            "scopes":[s for s in ROLE_SCOPES if is_super(u) or s!="all"],"min_rank":1 if is_super(u) else int(u["rank"])+1}

@app.post("/api/admin/roles")
def create_role(p:Payload,u=Depends(require_csrf)):
    if "ROLE_ADMIN" not in u["permissions"]: raise HTTPException(403,"Role administration permission required")
    d=p.data; name=str(d.get("name") or "").strip(); scope=d.get("scope_type") or "self"; codes=list(d.get("permissions") or [])
    if not name: raise HTTPException(400,"Role name is required")
    if scope not in ROLE_SCOPES: raise HTTPException(400,"Unknown visibility scope")
    rank=int(d["rank"]) if d.get("rank") not in (None,"") else int(row(select(func.max(roles.c.rank).label("m")))["m"] or 0)+10
    if not is_super(u) and (scope=="all" or rank<=int(u["rank"])): raise HTTPException(403,"New roles must rank below your own role and cannot see the whole organisation")
    ensure_grantable(u,codes)
    try: rid=execute(insert(roles).values(name=name,scope_type=scope,rank=rank,active=True,created_by=None if is_super(u) else u["id"]))
    except IntegrityError: raise HTTPException(400,"A role with this name already exists")
    set_role_permissions(rid,codes); audit(u["id"],"role",rid,"CREATE",{"name":name,"scope_type":scope,"rank":rank,"permissions":codes})
    return {"id":rid,"name":name,"scope_type":scope,"rank":rank,"permissions":codes}

@app.put("/api/admin/roles/{role_id}")
def update_role(role_id:int,p:Payload,u=Depends(require_csrf)):
    r=editable_role(u,role_id); d=p.data; vals={}
    if "name" in d:
        vals["name"]=str(d["name"] or "").strip()
        if not vals["name"]: raise HTTPException(400,"Role name is required")
    if "scope_type" in d:
        if d["scope_type"] not in ROLE_SCOPES: raise HTTPException(400,"Unknown visibility scope")
        vals["scope_type"]=d["scope_type"]
    if d.get("rank") not in (None,""): vals["rank"]=int(d["rank"])
    if not role_editable(u,{**r,**vals}): raise HTTPException(403,"Roles must rank below your own role and cannot see the whole organisation")
    codes=list(d["permissions"] or []) if "permissions" in d else None
    if codes is not None: ensure_grantable(u,codes)
    if vals:
        try: execute(update(roles).where(roles.c.id==role_id).values(**vals))
        except IntegrityError: raise HTTPException(400,"A role with this name already exists")
    if codes is not None: set_role_permissions(role_id,codes)
    audit(u["id"],"role",role_id,"UPDATE",d); return {"ok":True}

@app.put("/api/admin/roles/{role_id}/permissions")
def update_role_permissions(role_id:int,p:Payload,u=Depends(require_csrf)):
    editable_role(u,role_id); codes=p.data.get("permissions") or []; ensure_grantable(u,codes)
    set_role_permissions(role_id,codes)
    audit(u["id"],"role",role_id,"PERMISSIONS_UPDATE",{"permissions":codes}); return {"ok":True}

@app.delete("/api/admin/roles/{role_id}")
def delete_role(role_id:int,u=Depends(require_csrf)):
    r=editable_role(u,role_id)
    if row(select(users.c.id).where(users.c.role_id==role_id).limit(1)): raise HTTPException(400,"Move the users in this role to another role before deleting it")
    with engine.begin() as c:
        c.execute(delete(field_permissions).where(field_permissions.c.role_id==role_id))
        c.execute(delete(role_permissions).where(role_permissions.c.role_id==role_id))
        c.execute(delete(roles).where(roles.c.id==role_id))
    audit(u["id"],"role",role_id,"DELETE",{"name":r["name"]}); return {"ok":True}

@app.get("/api/companies")
def list_companies(u=Depends(require_perm("COMPANY_VIEW"))):
    ct=select(func.count()).select_from(contacts).where(contacts.c.company_id==companies.c.id).scalar_subquery()
    ld=select(func.count()).select_from(leads).where(leads.c.company_id==companies.c.id).scalar_subquery()
    op=select(func.count()).select_from(opportunities).where(opportunities.c.company_id==companies.c.id).scalar_subquery()
    return rows(select(companies,ct.label("contact_count"),ld.label("lead_count"),op.label("opportunity_count")).where(companies.c.status!="Merged").order_by(companies.c.name))

def duplicate_companies(name:str|None,website:str|None):
    nn=normalize_name(name); domain=domain_from_url(website); candidates=[]
    for c in rows(select(companies).where(companies.c.status!="Merged")):
        score=0; reasons=[]
        if nn and c["normalized_name"]==nn: score+=0.75; reasons.append("same normalized name")
        elif nn and (nn in c["normalized_name"] or c["normalized_name"] in nn): score+=0.45; reasons.append("similar name")
        if domain and c.get("domain")==domain: score+=0.55; reasons.append("same website domain")
        if score>=0.45: candidates.append({"company":c,"score":round(min(score,1),2),"reasons":reasons})
    return sorted(candidates,key=lambda x:x["score"],reverse=True)

@app.get("/api/data-quality/company-duplicates")
def company_duplicates(name:str="",website:str="",u=Depends(require_perm("COMPANY_VIEW"))): return duplicate_companies(name,website)

@app.post("/api/companies")
def create_company(p:Payload,u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403,"Company edit permission required")
    d=p.data
    if not d.get("name") or not d.get("vertical"): raise HTTPException(400,"Company name and vertical are required")
    dups=duplicate_companies(d["name"],d.get("website"))
    if dups and dups[0]["score"]>=0.75: raise HTTPException(409,f"Potential duplicate company: {dups[0]['company']['name']}. Reuse the existing company or review duplicates.")
    cid=execute(insert(companies).values(name=d["name"].strip(),normalized_name=normalize_name(d["name"]),vertical=classify_vertical(d["vertical"]),website=d.get("website"),domain=domain_from_url(d.get("website")),linkedin_url=d.get("linkedin_url"),external_url=d.get("external_url"),region=d.get("region"),country=d.get("country"),state=d.get("state"),city=d.get("city"),remarks=d.get("remarks"),status="Active",created_by=u["id"]))
    audit(u["id"],"company",cid,"CREATE",d); return row(select(companies).where(companies.c.id==cid))

@app.get("/api/companies/{company_id}")
def company_detail(company_id:int,u=Depends(require_perm("COMPANY_VIEW"))):
    c=row(select(companies).where(companies.c.id==company_id));
    if not c: raise HTTPException(404,"Company not found")
    rel=can_access_company_relationship(u,company_id)
    return {"company":c,"contacts":[mask_fields(u,"contact",x) for x in rows(select(contacts).where(contacts.c.company_id==company_id).order_by(contacts.c.is_primary.desc(),contacts.c.id))] if rel else [],"relationship_access":rel,"leads":[x for x in lead_rows(u) if x["company_id"]==company_id],"opportunities":[x for x in opportunity_rows(u) if x["company_id"]==company_id]}

@app.put("/api/companies/{company_id}")
def update_company(company_id:int,p:Payload,u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403,"Company edit permission required")
    if not row(select(companies.c.id).where(companies.c.id==company_id)): raise HTTPException(404,"Company not found")
    if not can_access_company_relationship(u,company_id): raise HTTPException(403,"Company relationship edit denied")
    d=p.data; vals={k:d[k] for k in ("name","vertical","website","linkedin_url","external_url","region","country","state","city","remarks","status") if k in d}
    for k in ("name","vertical"):
        if k in vals:
            vals[k]=_clean_text(vals[k],220 if k=="name" else None)
            if not vals[k]: raise HTTPException(400,f"Company {k} is required")
    if "vertical" in vals: vals["vertical"]=classify_vertical(vals["vertical"])
    for k,label,n in (("region","Region",80),("country","Country",100),("state","State",100),("city","City",100),("remarks","Company notes",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    for k,label in (("website","Website"),("linkedin_url","Company LinkedIn page"),("external_url","Other link")):
        if k in vals: vals[k]=_clean_url(vals[k],label)
    if "name" in vals:
        vals["normalized_name"]=normalize_name(vals["name"])
        clash=row(select(companies.c.id,companies.c.name).where(and_(companies.c.normalized_name==vals["normalized_name"],companies.c.id!=company_id,companies.c.status!="Merged")))
        if clash: raise HTTPException(409,f"Another company is already named {clash['name']}")
    if "website" in vals: vals["domain"]=domain_from_url(vals["website"])
    vals["updated_at"]=utcnow(); execute(update(companies).where(companies.c.id==company_id).values(**vals)); audit(u["id"],"company",company_id,"UPDATE",d); return row(select(companies).where(companies.c.id==company_id))

@app.post("/api/companies/{company_id}/contacts")
def add_contact(company_id:int,p:Payload,u=Depends(require_csrf)):
    if "CONTACT_EDIT" not in u["permissions"]: raise HTTPException(403,"Contact edit permission required")
    if not can_access_company_relationship(u,company_id): raise HTTPException(403,"Company relationship access denied")
    d=p.data; ensure_fields_editable(u,"contact",d)
    if not d.get("name"): raise HTTPException(400,"Contact name is required")
    ne=normalize_email(d.get("email"))
    if ne and row(select(contacts.c.id).where(and_(contacts.c.company_id==company_id,contacts.c.normalized_email==ne,contacts.c.active==True))): raise HTTPException(409,"A contact with this email already exists for the company")
    cid=execute(insert(contacts).values(company_id=company_id,name=d["name"],designation=d.get("designation"),department=d.get("department"),email=d.get("email"),normalized_email=ne,phone=d.get("phone"),linkedin_url=d.get("linkedin_url"),location=d.get("location"),remarks=d.get("remarks"),is_primary=bool(d.get("is_primary")),active=True,created_by=u["id"]))
    audit(u["id"],"contact",cid,"CREATE",d); return mask_fields(u,"contact",row(select(contacts).where(contacts.c.id==cid)))

@app.put("/api/contacts/{contact_id}")
def update_contact(contact_id:int,p:Payload,u=Depends(require_csrf)):
    if "CONTACT_EDIT" not in u["permissions"]: raise HTTPException(403,"Contact edit permission required")
    cr=row(select(contacts.c.company_id).where(contacts.c.id==contact_id))
    if not cr: raise HTTPException(404,"Contact not found")
    if not can_access_company_relationship(u,int(cr["company_id"])): raise HTTPException(403,"Contact relationship access denied")
    d=p.data; ensure_fields_editable(u,"contact",d); vals={k:d[k] for k in ("name","designation","department","email","phone","linkedin_url","location","remarks","is_primary","active") if k in d}
    if "name" in vals:
        vals["name"]=_clean_text(vals["name"],180)
        if not vals["name"]: raise HTTPException(400,"Contact name is required")
    for k,n in (("designation",180),("department",120),("phone",80),("location",220),("remarks",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    if "linkedin_url" in vals: vals["linkedin_url"]=_clean_url(vals["linkedin_url"],"LinkedIn profile")
    if "email" in vals:
        vals["email"]=_clean_text(vals["email"],190)
        if vals["email"] and ("@" not in vals["email"] or " " in vals["email"]): raise HTTPException(400,"Email address is not valid")
        vals["normalized_email"]=normalize_email(vals["email"])
        if vals["normalized_email"] and row(select(contacts.c.id).where(and_(contacts.c.company_id==cr["company_id"],contacts.c.normalized_email==vals["normalized_email"],contacts.c.active==True,contacts.c.id!=contact_id))):
            raise HTTPException(409,"Another contact at this company already uses this email")
    if "is_primary" in vals: vals["is_primary"]=bool(vals["is_primary"])
    if "active" in vals: vals["active"]=bool(vals["active"])
    if vals.get("is_primary"): execute(update(contacts).where(and_(contacts.c.company_id==cr["company_id"],contacts.c.id!=contact_id)).values(is_primary=False,updated_at=utcnow()))
    vals["updated_at"]=utcnow(); execute(update(contacts).where(contacts.c.id==contact_id).values(**vals)); audit(u["id"],"contact",contact_id,"UPDATE",d); return mask_fields(u,"contact",row(select(contacts).where(contacts.c.id==contact_id)))

@app.post("/api/companies/merge")
def merge_companies(p:Payload,u=Depends(require_csrf)):
    if "COMPANY_MERGE" not in u["permissions"]: raise HTTPException(403,"Company merge permission required")
    src=int(p.data.get("source_company_id")); tgt=int(p.data.get("target_company_id"));
    if src==tgt: raise HTTPException(400,"Source and target must differ")
    with engine.begin() as c:
        c.execute(update(contacts).where(contacts.c.company_id==src).values(company_id=tgt,updated_at=utcnow()))
        c.execute(update(leads).where(leads.c.company_id==src).values(company_id=tgt,updated_at=utcnow()))
        c.execute(update(opportunities).where(opportunities.c.company_id==src).values(company_id=tgt,updated_at=utcnow()))
        c.execute(update(companies).where(companies.c.id==src).values(status="Merged",updated_at=utcnow()))
    audit(u["id"],"company",src,"MERGE",{"target_company_id":tgt}); return {"ok":True,"target_company_id":tgt}

@app.post("/api/leads/full")
def create_lead_full(p:Payload,u=Depends(require_csrf)):
    if "LEAD_CREATE" not in u["permissions"]: raise HTTPException(403,"Lead create permission required")
    d=p.data; l=d.get("lead") or {}; owner_id=int(l.get("owner_id") or u["id"])
    if not can_assign(u,owner_id): raise HTTPException(403,"You cannot assign this lead to that user")
    co_owner_ids=[i for i in parse_person_ids(l.get("co_owner_ids"),"Additional owners") if i!=owner_id]
    if co_owner_ids: plan_people(u,"lead",None,owner_id,co_owner_ids,"owners")
    company_id=d.get("company_id")
    if company_id:
        if not row(select(companies.c.id).where(companies.c.id==int(company_id))): raise HTTPException(404,"Company not found")
        company_id=int(company_id)
    else:
        comp=d.get("company") or {}
        if not comp.get("name") or not comp.get("vertical"): raise HTTPException(400,"Company name and vertical are required")
        dups=duplicate_companies(comp["name"],comp.get("website"))
        if dups and dups[0]["score"]>=0.75: raise HTTPException(409,f"Potential duplicate company: {dups[0]['company']['name']}. Select the existing company.")
        company_id=execute(insert(companies).values(name=comp["name"].strip(),normalized_name=normalize_name(comp["name"]),vertical=classify_vertical(comp["vertical"]),website=comp.get("website"),domain=domain_from_url(comp.get("website")),linkedin_url=comp.get("linkedin_url"),external_url=comp.get("external_url"),region=comp.get("region") or l.get("region"),country=comp.get("country") or l.get("country"),state=comp.get("state") or l.get("state"),city=comp.get("city") or l.get("city"),remarks=comp.get("remarks"),status="Active",created_by=u["id"]))
    lead_id=execute(insert(leads).values(company_id=company_id,owner_id=owner_id,temperature=l.get("temperature") or "Warm",source=l.get("source") or "LinkedIn",source_detail=l.get("source_detail"),status=l.get("status") or "New",region=l.get("region"),country=l.get("country"),state=l.get("state"),city=l.get("city"),next_follow_up=l.get("next_follow_up"),remarks=l.get("remarks"),created_by=u["id"]))
    if co_owner_ids: apply_people(u,"lead",lead_id,co_owner_ids,[])
    for idx,ct in enumerate(d.get("contacts") or []):
        if ct.get("name"):
            ne=normalize_email(ct.get("email"))
            if ne and row(select(contacts.c.id).where(and_(contacts.c.company_id==company_id,contacts.c.normalized_email==ne,contacts.c.active==True))): continue
            execute(insert(contacts).values(company_id=company_id,name=ct["name"],designation=ct.get("designation"),department=ct.get("department"),email=ct.get("email"),normalized_email=ne,phone=ct.get("phone"),linkedin_url=ct.get("linkedin_url"),location=ct.get("location"),remarks=ct.get("remarks"),is_primary=bool(ct.get("is_primary") or idx==0),active=True,created_by=u["id"]))
    audit(u["id"],"lead",lead_id,"CREATE",{"company_id":company_id,"owner_id":owner_id,"co_owner_ids":co_owner_ids}); return lead_detail(lead_id,u)

@app.get("/api/leads")
def list_leads(u=Depends(require_perm("LEAD_VIEW"))): return lead_rows(u)

@app.get("/api/leads/{lead_id}")
def lead_detail(lead_id:int,u=Depends(require_perm("LEAD_VIEW"))):
    if not can_view_lead(u,lead_id): raise HTTPException(403,"You do not have access to this lead")
    owner=users.alias("owner")
    l=row(select(leads,companies.c.name.label("company_name"),companies.c.vertical,companies.c.website,companies.c.linkedin_url,companies.c.external_url,companies.c.remarks.label("company_remarks"),owner.c.name.label("owner_name")).select_from(leads.join(companies,companies.c.id==leads.c.company_id).join(owner,owner.c.id==leads.c.owner_id)).where(leads.c.id==lead_id))
    cts=[mask_fields(u,"contact",x) for x in rows(select(contacts).where(and_(contacts.c.company_id==l["company_id"],contacts.c.active==True)).order_by(contacts.c.is_primary.desc(),contacts.c.id))]
    mts=rows(select(meetings).where(meetings.c.lead_id==lead_id).order_by(meetings.c.meeting_date.desc(),meetings.c.id.desc()))
    ms=rows(select(moms).where(moms.c.lead_id==lead_id).order_by(moms.c.id.desc()))
    att_by_mom={}
    for a in rows(select(mom_attachments.c.id,mom_attachments.c.mom_id,mom_attachments.c.filename,mom_attachments.c.size_bytes,mom_attachments.c.uploaded_by,mom_attachments.c.created_at,users.c.name.label("uploaded_by_name")).select_from(mom_attachments.join(users,users.c.id==mom_attachments.c.uploaded_by)).where(mom_attachments.c.lead_id==lead_id).order_by(mom_attachments.c.id)):
        a["can_delete"]=a["uploaded_by"]==u["id"] or u["role"] in ("Super Admin","Admin")
        att_by_mom.setdefault(a["mom_id"],[]).append(a)
    for mo in ms: mo["attachments"]=att_by_mom.get(mo["id"],[])
    aa=users.alias("aa")
    acts=rows(select(actions,aa.c.name.label("assigned_to_name")).select_from(actions.join(aa,aa.c.id==actions.c.assigned_to)).where(actions.c.lead_id==lead_id).order_by(actions.c.due_date,actions.c.id.desc()))
    for a in acts: a["overdue"]=a["status"] not in ("Completed","Cancelled") and a["due_date"]<today_str()
    attach_people(acts,"action","co_assignees"); l["co_owners"]=people_map("lead",[lead_id]).get(lead_id,[])
    opps=[x for x in opportunity_rows(u) if x["lead_id"]==lead_id]
    fs=[]
    for o in opps:
        ff=rows(select(followups).where(followups.c.opportunity_id==o["id"]).order_by(followups.c.follow_up_date.desc(),followups.c.id.desc()))
        for f in ff: f["opportunity_name"]=o["name"]; f["owner_name"]=user_name(f["owner_id"])
        fs.extend(ff)
    docs=rows(select(documents).where(or_(and_(documents.c.entity_type=="lead",documents.c.entity_id==lead_id),and_(documents.c.entity_type=="company",documents.c.entity_id==l["company_id"]))).order_by(documents.c.id.desc()))
    timeline=[]
    for m in mts: timeline.append({"date":m["meeting_date"],"type":"Meeting","title":m["meeting_type"],"detail":m.get("remarks") or m.get("purpose")})
    for mo in ms: timeline.append({"date":str(mo["created_at"])[:10],"type":"MoM","title":"Minutes of Meeting","detail":mo.get("summary")})
    for a in acts: timeline.append({"date":a["action_date"],"type":"Action","title":a["description"],"detail":f"{', '.join([a['assigned_to_name']]+[p['name'] for p in a['co_assignees']])} · {a['status']} · due {a['due_date']}"})
    for o in opps: timeline.append({"date":str(o["created_at"])[:10],"type":"Opportunity","title":o["name"],"detail":f"{o['status']} · {o['forecast_category']}"})
    for f in fs: timeline.append({"date":f["follow_up_date"],"type":"Follow-up","title":f["opportunity_name"],"detail":f.get("response") or f.get("remarks")})
    timeline.sort(key=lambda x:x["date"] or "",reverse=True)
    # Role rules (unchanged from before the edit form existed):
    #  prospect fields  -> LEAD_EDIT and the owner is in the user's scope (or shared with edit access)
    #  owner            -> also LEAD_REASSIGN
    #  company/contacts -> COMPANY_EDIT / CONTACT_EDIT and the user can see a prospect of that company
    #  delete           -> Super Admin or Admin who can edit the prospect
    # Last time the Overview content was saved: an edit of this prospect or of its company (from the audit trail,
    # because leads.updated_at also moves when meetings, MoM follow-ups or opportunities are added)
    last_edit=row(select(func.max(audit_logs.c.created_at).label("at")).where(and_(audit_logs.c.action=="UPDATE",or_(
        and_(audit_logs.c.entity_type=="lead",audit_logs.c.entity_id==lead_id),
        and_(audit_logs.c.entity_type=="company",audit_logs.c.entity_id==l["company_id"])))))
    l["last_edited_at"]=iso_utc((last_edit or {}).get("at"))
    l["created_at_utc"]=iso_utc(l.get("created_at"))
    editable=can_edit_lead(u,lead_id)
    related=can_access_company_relationship(u,l["company_id"])
    perms={"can_edit":editable,"can_edit_company":related and "COMPANY_EDIT" in u["permissions"],"can_edit_contacts":related and "CONTACT_EDIT" in u["permissions"],
           "can_reassign":editable and "LEAD_REASSIGN" in u["permissions"],"can_manage_owners":editable and "LEAD_REASSIGN" in u["permissions"] and is_admin_role(u),"can_delete":editable and u["role"] in ("Super Admin","Admin")}
    # Contact fields this role may not see or change (field permissions); the edit form keeps them locked
    perms["locked_contact_fields"]=[f for f in ("name","designation","email","phone","linkedin_url") if not all(field_access(u,"contact",f))]
    return {"lead":l,"contacts":cts,"meetings":mts,"moms":ms,"actions":acts,"opportunities":opps,"followups":fs,"documents":docs,"timeline":timeline,"permissions":perms}

@app.put("/api/leads/{lead_id}")
def update_lead(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_lead(u,lead_id): raise HTTPException(403,"You cannot edit this lead")
    d=p.data; vals={k:d[k] for k in ("temperature","source","source_detail","status","region","country","state","city","next_follow_up","remarks") if k in d}
    if "temperature" in vals and vals["temperature"] not in LEAD_TEMPERATURES: raise HTTPException(400,"Signal must be Hot, Warm or Cold")
    if "status" in vals and vals["status"] not in LEAD_STATUSES: raise HTTPException(400,"Invalid prospect status")
    if "source" in vals:
        vals["source"]=_clean_text(vals["source"],80)
        if not vals["source"]: raise HTTPException(400,"Source is required")
    for k,n in (("source_detail",255),("region",80),("country",100),("state",100),("city",100),("remarks",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    if "next_follow_up" in vals:
        nf=_clean_text(vals["next_follow_up"])
        if nf:
            try: nf=datetime.strptime(nf,"%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError: raise HTTPException(400,"Next follow-up must be a valid date")
        vals["next_follow_up"]=nf
    if "owner_id" in d:
        oid=int(d["owner_id"])
        if "LEAD_REASSIGN" not in u["permissions"] or not can_assign(u,oid): raise HTTPException(403,"You cannot reassign this lead")
        vals["owner_id"]=oid
    added=removed=[]
    if "co_owner_ids" in d:
        primary=vals.get("owner_id") or row(select(leads.c.owner_id).where(leads.c.id==lead_id))["owner_id"]
        added,removed=plan_people(u,"lead",lead_id,primary,parse_person_ids(d["co_owner_ids"],"Additional owners"),"owners")
        if (added or removed) and "LEAD_REASSIGN" not in u["permissions"]: raise HTTPException(403,"You cannot reassign this lead")
    vals["updated_at"]=utcnow(); execute(update(leads).where(leads.c.id==lead_id).values(**vals))
    if added or removed: apply_people(u,"lead",lead_id,added,removed)
    if "owner_id" in vals: drop_person("lead",lead_id,vals["owner_id"])
    audit(u["id"],"lead",lead_id,"UPDATE",d); return lead_detail(lead_id,u)

@app.delete("/api/leads/{lead_id}")
def delete_lead(lead_id:int,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only Super Admin and Admin can delete leads")
    l=row(select(leads,companies.c.name.label("company_name")).select_from(leads.join(companies,companies.c.id==leads.c.company_id)).where(leads.c.id==lead_id))
    if not l: raise HTTPException(404,"Lead not found")
    if not can_edit_lead(u,lead_id): raise HTTPException(403,"You cannot delete this lead")
    opp_ids=[r["id"] for r in rows(select(opportunities.c.id).where(opportunities.c.lead_id==lead_id))]
    if opp_ids:
        execute(delete(followups).where(followups.c.opportunity_id.in_(opp_ids)))
        execute(delete(opportunity_team).where(opportunity_team.c.opportunity_id.in_(opp_ids)))
        execute(delete(opportunities).where(opportunities.c.lead_id==lead_id))
    clear_people("action",[r["id"] for r in rows(select(actions.c.id).where(actions.c.lead_id==lead_id))])
    clear_people("lead",[lead_id])
    execute(delete(actions).where(actions.c.lead_id==lead_id))
    execute(delete(mom_attachments).where(mom_attachments.c.lead_id==lead_id))
    execute(delete(moms).where(moms.c.lead_id==lead_id))
    execute(delete(meetings).where(meetings.c.lead_id==lead_id))
    execute(delete(record_shares).where(and_(record_shares.c.entity_type=="lead",record_shares.c.entity_id==lead_id)))
    execute(delete(leads).where(leads.c.id==lead_id))
    audit(u["id"],"lead",lead_id,"DELETE",{"company_name":l.get("company_name","")}); return {"ok":True}

@app.post("/api/leads/{lead_id}/share")
def share_lead(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if "SHARE_RECORD" not in u["permissions"] or not can_view_lead(u,lead_id): raise HTTPException(403,"Record-share permission required")
    target=int(p.data.get("user_id")); level=p.data.get("access_level") or "view"
    if not is_super(u) and org_root(target)!=org_root(u["id"]): raise HTTPException(403,"Records can only be shared within your own organisation")
    with engine.begin() as c:
        existing=c.execute(select(record_shares.c.id).where(and_(record_shares.c.entity_type=="lead",record_shares.c.entity_id==lead_id,record_shares.c.user_id==target))).fetchone()
        if existing: c.execute(update(record_shares).where(record_shares.c.id==existing.id).values(access_level=level))
        else: c.execute(insert(record_shares).values(entity_type="lead",entity_id=lead_id,user_id=target,access_level=level,created_by=u["id"]))
    audit(u["id"],"lead",lead_id,"SHARE",{"user_id":target,"access_level":level}); return {"ok":True}

@app.post("/api/leads/{lead_id}/meetings")
def add_meeting(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"] or not can_view_lead(u,lead_id): raise HTTPException(403,"Meeting permission denied")
    d=p.data
    if not d.get("meeting_date") or not d.get("meeting_type"): raise HTTPException(400,"Meeting date and type are required")
    mid=execute(insert(meetings).values(lead_id=lead_id,opportunity_id=d.get("opportunity_id") or None,meeting_date=d["meeting_date"],meeting_time=d.get("meeting_time"),meeting_type=d["meeting_type"],status=d.get("status") or "Scheduled",purpose=d.get("purpose"),customer_participants=d.get("customer_participants"),jsan_participants=d.get("jsan_participants"),remarks=d.get("remarks"),created_by=u["id"]))
    execute(update(leads).where(leads.c.id==lead_id).values(updated_at=utcnow())); audit(u["id"],"meeting",mid,"CREATE",d); return row(select(meetings).where(meetings.c.id==mid))

@app.post("/api/leads/{lead_id}/moms")
def add_mom(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"] or not can_view_lead(u,lead_id): raise HTTPException(403,"MoM permission denied")
    d=p.data
    if not d.get("summary"): raise HTTPException(400,"Discussion summary is required")
    mid=execute(insert(moms).values(meeting_id=d.get("meeting_id") or None,lead_id=lead_id,summary=d["summary"],customer_requirements=d.get("customer_requirements"),jsan_commitments=d.get("jsan_commitments"),customer_commitments=d.get("customer_commitments"),risks=d.get("risks"),next_steps=d.get("next_steps"),follow_up_date=d.get("follow_up_date"),created_by=u["id"]))
    if d.get("follow_up_date"): execute(update(leads).where(leads.c.id==lead_id).values(next_follow_up=d["follow_up_date"],updated_at=utcnow()))
    audit(u["id"],"mom",mid,"CREATE",d); return row(select(moms).where(moms.c.id==mid))

# ── MoM Word attachments ──────────────────────────────────────────────────────
DOCX_MIME="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MOM_ATTACHMENT_MAX_BYTES=10*1024*1024
MOM_ATTACHMENT_MAX_UNZIPPED=100*1024*1024
MOM_ATTACHMENTS_PER_MOM=10

def _clean_filename(name:str)->str:
    base=os.path.basename(str(name or "").replace("\\","/"))
    base="".join(ch for ch in base if ch.isprintable() and ch not in '<>:"/\\|?*').strip(" .")
    if len(base)>200:
        stem,ext=os.path.splitext(base); base=stem[:200-len(ext)]+ext
    return base or "minutes.docx"

def _validate_docx(filename:str,data:bytes):
    """Accept only a genuine, macro-free Word .docx: correct extension, zip signature, Word parts, sane unzipped size."""
    if not filename.lower().endswith(".docx"): raise HTTPException(400,"Only Word .docx files can be attached")
    if not data: raise HTTPException(400,"The file is empty")
    if len(data)>MOM_ATTACHMENT_MAX_BYTES: raise HTTPException(413,"The file is larger than 10 MB")
    if not data.startswith(b"PK\x03\x04"): raise HTTPException(400,"This file is not a valid Word .docx document")
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos=z.infolist()
            names={i.filename for i in infos}
            if sum(i.file_size for i in infos)>MOM_ATTACHMENT_MAX_UNZIPPED: raise HTTPException(400,"The document is too large once opened")
            if "[Content_Types].xml" not in names or "word/document.xml" not in names: raise HTTPException(400,"This file is not a valid Word .docx document")
            if any(n.lower().endswith("vbaproject.bin") for n in names) or b"macroEnabled" in z.read("[Content_Types].xml"): raise HTTPException(400,"Macro-enabled Word documents are not allowed")
    except HTTPException: raise
    except Exception: raise HTTPException(400,"This file is not a valid Word .docx document")

# RFP documents accept a broader set of common business file types (unlike MoM attachments, which
# stay .docx-only). Zip-based office formats get the same zip-signature/macro checks as .docx;
# other types get a light signature check where one exists. Deliberately excludes HTML/SVG/script/
# executable types so an "inline" preview response can never execute attacker content.
RFP_ALLOWED_EXTENSIONS = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".ppt": "application/vnd.ms-powerpoint",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
    ".zip": "application/zip",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".msg": "application/vnd.ms-outlook",
}

def _validate_rfp_file(filename: str, data: bytes) -> str:
    if not data: raise HTTPException(400, "The file is empty")
    if len(data) > MOM_ATTACHMENT_MAX_BYTES: raise HTTPException(413, "The file is larger than 10 MB")
    ext = os.path.splitext(filename.lower())[1]
    if ext not in RFP_ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"'{ext or 'this file type'}' is not supported. Allowed types: " + ", ".join(sorted(e.lstrip('.') for e in RFP_ALLOWED_EXTENSIONS)))
    if ext in (".docx", ".xlsx", ".pptx", ".zip"):
        if not data.startswith(b"PK\x03\x04"): raise HTTPException(400, "This file is not a valid document")
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = z.infolist()
                if sum(i.file_size for i in infos) > MOM_ATTACHMENT_MAX_UNZIPPED: raise HTTPException(400, "The document is too large once opened")
                if any(i.filename.lower().endswith("vbaproject.bin") for i in infos): raise HTTPException(400, "Macro-enabled documents are not allowed")
        except HTTPException: raise
        except Exception: raise HTTPException(400, "This file is not a valid document")
    elif ext == ".pdf":
        if not data.startswith(b"%PDF-"): raise HTTPException(400, "This file is not a valid PDF")
    return RFP_ALLOWED_EXTENSIONS[ext]

def _mom_for(u,mom_id:int):
    m=row(select(moms.c.id,moms.c.lead_id).where(moms.c.id==mom_id))
    if not m or not can_view_lead(u,m["lead_id"]): raise HTTPException(404,"Minutes of Meeting not found")
    return m

@app.post("/api/moms/{mom_id}/attachments")
def upload_mom_attachment(mom_id:int,file:UploadFile=File(...),u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"]: raise HTTPException(403,"MoM permission denied")
    m=_mom_for(u,mom_id)
    count=(row(select(func.count().label("n")).select_from(mom_attachments).where(mom_attachments.c.mom_id==mom_id)) or {}).get("n",0)
    if count>=MOM_ATTACHMENTS_PER_MOM: raise HTTPException(400,f"A MoM can have at most {MOM_ATTACHMENTS_PER_MOM} attachments")
    data=file.file.read(MOM_ATTACHMENT_MAX_BYTES+1)
    filename=_clean_filename(file.filename)
    _validate_docx(filename,data)
    digest=hashlib.sha256(data).hexdigest()
    aid=execute(insert(mom_attachments).values(mom_id=mom_id,lead_id=m["lead_id"],filename=filename,content_type=DOCX_MIME,size_bytes=len(data),sha256=digest,data=data,uploaded_by=u["id"]))
    audit(u["id"],"mom_attachment",aid,"CREATE",{"mom_id":mom_id,"filename":filename,"size_bytes":len(data),"sha256":digest})
    return {"id":aid,"mom_id":mom_id,"filename":filename,"size_bytes":len(data),"uploaded_by":u["id"],"uploaded_by_name":u["name"],"can_delete":True}

@app.get("/api/moms/{mom_id}/attachments/{attachment_id}")
def download_mom_attachment(mom_id:int,attachment_id:int,u=Depends(require_perm("LEAD_VIEW"))):
    _mom_for(u,mom_id)
    a=row(select(mom_attachments).where(and_(mom_attachments.c.id==attachment_id,mom_attachments.c.mom_id==mom_id)))
    if not a: raise HTTPException(404,"Attachment not found")
    from urllib.parse import quote
    ascii_name="".join(ch if ch.isascii() and ch.isprintable() and ch not in '"\\;' else "_" for ch in a["filename"])
    return Response(content=bytes(a["data"]),media_type=DOCX_MIME,headers={
        "Content-Disposition":f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(a['filename'])}",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@app.delete("/api/moms/{mom_id}/attachments/{attachment_id}")
def delete_mom_attachment(mom_id:int,attachment_id:int,u=Depends(require_csrf)):
    _mom_for(u,mom_id)
    a=row(select(mom_attachments.c.id,mom_attachments.c.filename,mom_attachments.c.uploaded_by).where(and_(mom_attachments.c.id==attachment_id,mom_attachments.c.mom_id==mom_id)))
    if not a: raise HTTPException(404,"Attachment not found")
    if a["uploaded_by"]!=u["id"] and u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only the uploader, Super Admin or Admin can remove this file")
    execute(delete(mom_attachments).where(mom_attachments.c.id==attachment_id))
    audit(u["id"],"mom_attachment",attachment_id,"DELETE",{"mom_id":mom_id,"filename":a["filename"]}); return {"ok":True}

@app.get("/api/meetings")
def list_meetings(u=Depends(require_perm("LEAD_VIEW"))):
    out=[]
    for m in rows(select(meetings,companies.c.name.label("company_name"),leads.c.owner_id).select_from(meetings.join(leads,leads.c.id==meetings.c.lead_id).join(companies,companies.c.id==leads.c.company_id)).order_by(meetings.c.meeting_date.desc())):
        if can_view_lead(u,m["lead_id"]): out.append(m)
    return out

@app.get("/api/actions")
def list_actions(filter:str=Query(default="all"),u=Depends(current_user)):
    aa=users.alias("aa"); cr=users.alias("cr")
    base=rows(select(actions,companies.c.name.label("company_name"),leads.c.temperature,aa.c.name.label("assigned_to_name"),cr.c.name.label("created_by_name")).select_from(actions.join(leads,leads.c.id==actions.c.lead_id).join(companies,companies.c.id==leads.c.company_id).join(aa,aa.c.id==actions.c.assigned_to).join(cr,cr.c.id==actions.c.created_by)).order_by(actions.c.due_date))
    out=[]; t=today_str(); co=people_map("action")
    for a in base:
        a["co_assignees"]=co.get(a["id"],[])
        visible=is_assignee(a,u["id"]) or can_view_lead(u,a["lead_id"])
        if not visible: continue
        a["overdue"]=a["status"] not in ("Completed","Cancelled") and a["due_date"]<t
        if filter=="my" and not is_assignee(a,u["id"]): continue
        if filter=="overdue" and not a["overdue"]: continue
        if filter=="today" and not (a["status"] not in ("Completed","Cancelled") and a["due_date"]==t): continue
        if filter=="upcoming" and not (a["status"] not in ("Completed","Cancelled") and a["due_date"]>t): continue
        if filter=="completed" and a["status"]!="Completed": continue
        out.append(a)
    return out

@app.post("/api/leads/{lead_id}/actions")
def add_action(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if "ACTION_EDIT" not in u["permissions"] or not can_view_lead(u,lead_id): raise HTTPException(403,"Action permission denied")
    d=p.data; assigned=int(d.get("assigned_to") or u["id"])
    if not can_assign(u,assigned): raise HTTPException(403,"You cannot assign this action to that user")
    if not d.get("description") or not d.get("due_date"): raise HTTPException(400,"Action description and due date are required")
    co_ids=[i for i in parse_person_ids(d.get("co_assignee_ids"),"Additional assignees") if i!=assigned]
    if co_ids: plan_people(u,"action",None,assigned,co_ids,"assignees")
    pod=_optional_date(d.get("post_overdue_date"),"Post overdue date")
    aid=execute(insert(actions).values(lead_id=lead_id,opportunity_id=d.get("opportunity_id") or None,action_date=d.get("action_date") or today_str(),description=d["description"],assigned_to=assigned,due_date=d["due_date"],status=d.get("status") or "Open",priority=d.get("priority") or "Medium",remarks=d.get("remarks"),post_overdue_date=pod,created_by=u["id"]))
    if co_ids: apply_people(u,"action",aid,co_ids,[])
    notify_assigned([assigned]+co_ids,"New action assigned",d["description"],"action",aid,d["due_date"]); audit(u["id"],"action",aid,"CREATE",d)
    return attach_people([row(select(actions).where(actions.c.id==aid))],"action","co_assignees")[0]

@app.put("/api/actions/{action_id}")
def update_action(action_id:int,p:Payload,u=Depends(require_csrf)):
    a=row(select(actions).where(actions.c.id==action_id));
    if not a: raise HTTPException(404,"Action not found")
    a["co_assignees"]=people_map("action",[action_id]).get(action_id,[])
    if "ACTION_EDIT" not in u["permissions"] or (not is_assignee(a,u["id"]) and not can_edit_lead(u,a["lead_id"])): raise HTTPException(403,"You cannot update this action")
    d=p.data; vals={k:d[k] for k in ("description","assigned_to","due_date","status","priority","remarks","completion_date") if k in d}
    if "post_overdue_date" in d: vals["post_overdue_date"]=_optional_date(d.get("post_overdue_date"),"Post overdue date")
    # Only an Admin/Super Admin may post the reply that is shown back to the assignee
    if "admin_reply" in d and u["role"] in ("Super Admin","Admin"): vals["admin_reply"]=(str(d["admin_reply"]).strip() or None) if d["admin_reply"] is not None else None
    if d.get("status")=="Completed" and not d.get("completion_date"): vals["completion_date"]=today_str()
    added=removed=[]
    if "co_assignee_ids" in d:
        primary=int(vals["assigned_to"]) if vals.get("assigned_to") else a["assigned_to"]
        added,removed=plan_people(u,"action",action_id,primary,parse_person_ids(d["co_assignee_ids"],"Additional assignees"),"assignees")
    vals["updated_at"]=utcnow(); execute(update(actions).where(actions.c.id==action_id).values(**vals))
    if added or removed: apply_people(u,"action",action_id,added,removed)
    if vals.get("assigned_to"): drop_person("action",action_id,int(vals["assigned_to"]))
    if added: notify_assigned(added,"Action assigned to you",vals.get("description") or a["description"],"action",action_id,vals.get("due_date") or a["due_date"])
    audit(u["id"],"action",action_id,"UPDATE",d); return attach_people([row(select(actions).where(actions.c.id==action_id))],"action","co_assignees")[0]

@app.delete("/api/actions/{action_id}")
def delete_action(action_id:int,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only Super Admin and Admin can delete actions")
    a=row(select(actions).where(actions.c.id==action_id))
    if not a: raise HTTPException(404,"Action not found")
    clear_people("action",[action_id])
    execute(delete(actions).where(actions.c.id==action_id))
    audit(u["id"],"action",action_id,"DELETE",{"description":a["description"]}); return {"ok":True}

# ── Generic actions: work not tied to a prospect (PPT, summit preparation, internal tasks) ──
GENERIC_ACTION_TYPES=["Presentation / PPT","Summit / event preparation","Proposal preparation","Internal meeting","Training","Documentation","Other"]
ACTION_STATUSES=("Open","In Progress","Completed","Cancelled")
ACTION_PRIORITIES=("Low","Medium","High","Critical")

def _valid_date(v):
    try: return datetime.strptime(str(v),"%Y-%m-%d").strftime("%Y-%m-%d")
    except Exception: return None

def _optional_date(v,label):
    """Validate an optional YYYY-MM-DD date; blank/None clears it."""
    if v is None or str(v).strip()=="": return None
    d=_valid_date(v)
    if not d: raise HTTPException(400,f"{label} must be a valid YYYY-MM-DD date")
    return d

def generic_action_access(u,a):
    """Same hierarchy rule as prospect actions: your own, ones you created, and your reporting team's."""
    ids=set(scope_user_ids(u)); co={p["id"] for p in a.get("co_assignees") or []}
    visible=is_super(u) or a["assigned_to"]==u["id"] or a["created_by"]==u["id"] or a["assigned_to"] in ids or a["created_by"] in ids or u["id"] in co or bool(co&ids)
    can_edit=visible and "ACTION_EDIT" in u["permissions"]
    can_delete=visible and (u["role"] in ("Super Admin","Admin") or a["created_by"]==u["id"])
    return visible,can_edit,can_delete

def generic_action_row(action_id,u):
    aa=users.alias("aa"); cr=users.alias("cr")
    r=row(select(generic_actions,aa.c.name.label("assigned_to_name"),cr.c.name.label("created_by_name")).select_from(generic_actions.join(aa,aa.c.id==generic_actions.c.assigned_to).join(cr,cr.c.id==generic_actions.c.created_by)).where(generic_actions.c.id==action_id))
    if r:
        attach_people([r],"generic_action","co_assignees")
        _,r["can_edit"],r["can_delete"]=generic_action_access(u,r)
        r["overdue"]=r["status"] not in ("Completed","Cancelled") and r["due_date"]<today_str()
    return r

@app.get("/api/generic-actions")
def list_generic_actions(filter:str=Query(default="all"),u=Depends(current_user)):
    aa=users.alias("aa"); cr=users.alias("cr")
    stmt=select(generic_actions,aa.c.name.label("assigned_to_name"),cr.c.name.label("created_by_name")).select_from(generic_actions.join(aa,aa.c.id==generic_actions.c.assigned_to).join(cr,cr.c.id==generic_actions.c.created_by))
    if not is_super(u):
        ids=scope_user_ids(u)
        co_visible=select(record_people.c.entity_id).where(and_(record_people.c.entity_type=="generic_action",record_people.c.user_id.in_(ids)))
        stmt=stmt.where(or_(generic_actions.c.assigned_to.in_(ids),generic_actions.c.created_by.in_(ids),generic_actions.c.id.in_(co_visible)))
    t=today_str(); out=[]; co=people_map("generic_action")
    for a in rows(stmt.order_by(generic_actions.c.due_date,generic_actions.c.id)):
        open_=a["status"] not in ("Completed","Cancelled")
        a["overdue"]=open_ and a["due_date"]<t
        a["co_assignees"]=co.get(a["id"],[])
        if filter=="my" and not is_assignee(a,u["id"]): continue
        if filter=="overdue" and not a["overdue"]: continue
        if filter=="today" and not (open_ and a["due_date"]==t): continue
        if filter=="upcoming" and not (open_ and a["due_date"]>t): continue
        if filter=="completed" and a["status"]!="Completed": continue
        _,a["can_edit"],a["can_delete"]=generic_action_access(u,a)
        out.append(a)
    return {"types":GENERIC_ACTION_TYPES,"can_create":"ACTION_EDIT" in u["permissions"],"items":out}

def _generic_action_values(d,partial:bool):
    vals={}
    if not partial or "title" in d:
        title=str(d.get("title") or "").strip()
        if not title: raise HTTPException(400,"Title is required")
        if len(title)>255: raise HTTPException(400,"Title must be 255 characters or fewer")
        vals["title"]=title
    if not partial or "due_date" in d:
        due=_valid_date(d.get("due_date"))
        if not due: raise HTTPException(400,"A valid due date is required")
        vals["due_date"]=due
    if not partial or "action_type" in d:
        action_type=str(d.get("action_type") or "").strip()
        if not action_type: raise HTTPException(400,"Type is required")
        if len(action_type)>60: raise HTTPException(400,"Type must be 60 characters or fewer")
        vals["action_type"]=action_type
    if not partial or "priority" in d:
        if d.get("priority") and d["priority"] not in ACTION_PRIORITIES: raise HTTPException(400,"Invalid priority")
        vals["priority"]=d.get("priority") or "Medium"
    if "status" in d or not partial:
        if d.get("status") and d["status"] not in ACTION_STATUSES: raise HTTPException(400,"Invalid status")
        vals["status"]=d.get("status") or "Open"
    for k in ("description","remarks"):
        if k in d: vals[k]=(str(d[k]).strip() or None) if d[k] is not None else None
    if "post_overdue_date" in d: vals["post_overdue_date"]=_optional_date(d.get("post_overdue_date"),"Post overdue date")
    return vals

@app.post("/api/generic-actions")
def create_generic_action(p:Payload,u=Depends(require_csrf)):
    if "ACTION_EDIT" not in u["permissions"]: raise HTTPException(403,"Action permission denied")
    d=p.data; vals=_generic_action_values(d,partial=False)
    assigned=int(d.get("assigned_to") or u["id"])
    if not can_assign(u,assigned): raise HTTPException(403,"You cannot assign this action to that user")
    co_ids=[i for i in parse_person_ids(d.get("co_assignee_ids"),"Additional assignees") if i!=assigned]
    if co_ids: plan_people(u,"generic_action",None,assigned,co_ids,"assignees")
    if vals["status"]=="Completed": vals["completion_date"]=today_str()
    aid=execute(insert(generic_actions).values(**vals,assigned_to=assigned,created_by=u["id"]))
    if co_ids: apply_people(u,"generic_action",aid,co_ids,[])
    notify_assigned([i for i in [assigned]+co_ids if i!=u["id"]],"New action assigned",vals["title"],"generic_action",aid,vals["due_date"])
    audit(u["id"],"generic_action",aid,"CREATE",{**vals,"assigned_to":assigned,"co_assignee_ids":co_ids})
    return generic_action_row(aid,u)

@app.put("/api/generic-actions/{action_id}")
def update_generic_action(action_id:int,p:Payload,u=Depends(require_csrf)):
    a=row(select(generic_actions).where(generic_actions.c.id==action_id))
    if not a: raise HTTPException(404,"Action not found")
    a["co_assignees"]=people_map("generic_action",[action_id]).get(action_id,[])
    visible,can_edit,_=generic_action_access(u,a)
    if not visible: raise HTTPException(404,"Action not found")
    if not can_edit: raise HTTPException(403,"You cannot update this action")
    d=p.data; vals=_generic_action_values(d,partial=True)
    # Only an Admin/Super Admin may post the reply that is shown back to the assignee
    if "admin_reply" in d and u["role"] in ("Super Admin","Admin"): vals["admin_reply"]=(str(d["admin_reply"]).strip() or None) if d["admin_reply"] is not None else None
    if d.get("assigned_to") and int(d["assigned_to"])!=a["assigned_to"]:
        assigned=int(d["assigned_to"])
        if not can_assign(u,assigned): raise HTTPException(403,"You cannot assign this action to that user")
        vals["assigned_to"]=assigned
        notify_assigned([assigned],"Action assigned to you",vals.get("title") or a["title"],"generic_action",action_id,vals.get("due_date") or a["due_date"])
    added=removed=[]
    if "co_assignee_ids" in d:
        added,removed=plan_people(u,"generic_action",action_id,vals.get("assigned_to",a["assigned_to"]),parse_person_ids(d["co_assignee_ids"],"Additional assignees"),"assignees")
    if vals.get("status")=="Completed" and a["status"]!="Completed": vals["completion_date"]=today_str()
    elif vals.get("status") and vals["status"]!="Completed": vals["completion_date"]=None
    vals["updated_at"]=utcnow()
    execute(update(generic_actions).where(generic_actions.c.id==action_id).values(**vals))
    if added or removed: apply_people(u,"generic_action",action_id,added,removed)
    if vals.get("assigned_to"): drop_person("generic_action",action_id,vals["assigned_to"])
    if added: notify_assigned(added,"Action assigned to you",vals.get("title") or a["title"],"generic_action",action_id,vals.get("due_date") or a["due_date"])
    audit(u["id"],"generic_action",action_id,"UPDATE",d)
    return generic_action_row(action_id,u)

@app.delete("/api/generic-actions/{action_id}")
def delete_generic_action(action_id:int,u=Depends(require_csrf)):
    a=row(select(generic_actions).where(generic_actions.c.id==action_id))
    if not a: raise HTTPException(404,"Action not found")
    a["co_assignees"]=people_map("generic_action",[action_id]).get(action_id,[])
    visible,_,can_delete=generic_action_access(u,a)
    if not visible: raise HTTPException(404,"Action not found")
    if not can_delete: raise HTTPException(403,"Only Super Admin, Admin or the creator can delete this action")
    clear_people("generic_action",[action_id])
    execute(delete(generic_actions).where(generic_actions.c.id==action_id))
    audit(u["id"],"generic_action",action_id,"DELETE",{"title":a["title"]}); return {"ok":True}

@app.get("/api/opportunities")
def list_opportunities(u=Depends(require_perm("OPPORTUNITY_VIEW"))): return opportunity_rows(u)

@app.get("/api/opportunities/{opp_id}")
def opportunity_detail(opp_id:int,u=Depends(require_perm("OPPORTUNITY_VIEW"))):
    if not can_view_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    os=[x for x in opportunity_rows(u) if x["id"]==opp_id]
    if not os: raise HTTPException(404,"Opportunity not found")
    fs=rows(select(followups).where(followups.c.opportunity_id==opp_id).order_by(followups.c.follow_up_date.desc(),followups.c.id.desc()))
    for f in fs: f["owner_name"]=user_name(f["owner_id"])
    tm=rows(select(opportunity_team.c.user_id,opportunity_team.c.team_role,users.c.name,roles.c.name.label("role")).select_from(opportunity_team.join(users,users.c.id==opportunity_team.c.user_id).join(roles,roles.c.id==users.c.role_id)).where(opportunity_team.c.opportunity_id==opp_id))
    docs=rows(select(documents).where(and_(documents.c.entity_type=="opportunity",documents.c.entity_id==opp_id)).order_by(documents.c.id.desc()))
    return {"opportunity":os[0],"followups":fs,"team":tm,"documents":docs}

@app.post("/api/leads/{lead_id}/opportunities")
def add_opportunity(lead_id:int,p:Payload,u=Depends(require_csrf)):
    if "OPPORTUNITY_EDIT" not in u["permissions"] or not can_view_lead(u,lead_id): raise HTTPException(403,"Opportunity permission denied")
    d=p.data; ensure_fields_editable(u,"opportunity",d); l=row(select(leads.c.company_id,leads.c.owner_id).where(leads.c.id==lead_id)); owner=int(d.get("owner_id") or l["owner_id"])
    if not can_assign(u,owner): raise HTTPException(403,"You cannot assign this opportunity to that user")
    if not d.get("name"): raise HTTPException(400,"Opportunity name is required")
    status=d.get("status") or "New Opportunity"; validate_outcome(status,d); amount=float(d.get("amount") or 0); prob=float(d.get("probability") or 10); fc=d.get("forecast_category") or forecast_from_status(status)
    oid=execute(insert(opportunities).values(lead_id=lead_id,company_id=l["company_id"],owner_id=owner,presales_owner_id=d.get("presales_owner_id") or None,name=d["name"],service_practice=d.get("service_practice"),status=status,forecast_category=fc,amount=amount,currency=d.get("currency") or "USD",probability=prob,weighted_value=amount*prob/100,expected_close_date=d.get("expected_close_date"),proposal_date=d.get("proposal_date"),last_follow_up_date=d.get("last_follow_up_date"),next_follow_up_date=d.get("next_follow_up_date"),follow_up_count=0,final_amount=d.get("final_amount"),lost_reason=d.get("lost_reason"),hold_reason=d.get("hold_reason"),hold_review_date=d.get("hold_review_date"),competitor=d.get("competitor"),remarks=d.get("remarks"),created_by=u["id"],closed_at=today_str() if status.startswith("Closed ") else None))
    if d.get("presales_owner_id"):
        execute(insert(opportunity_team).values(opportunity_id=oid,user_id=int(d["presales_owner_id"]),team_role="Presales Owner",created_by=u["id"]))
    execute(update(leads).where(leads.c.id==lead_id).values(status="Qualified",updated_at=utcnow())); audit(u["id"],"opportunity",oid,"CREATE",d); return opportunity_detail(oid,u)

@app.put("/api/opportunities/{opp_id}")
def update_opportunity(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_opp(u,opp_id): raise HTTPException(403,"You cannot edit this opportunity")
    old=row(select(opportunities).where(opportunities.c.id==opp_id)); d=p.data; ensure_fields_editable(u,"opportunity",d)
    if "owner_id" in d and int(d["owner_id"]) != int(old["owner_id"]):
        if not can_assign(u, int(d["owner_id"])): raise HTTPException(403,"You cannot assign this opportunity to that user")
    merged={**old,**d}; status=merged["status"]
    if status.startswith("Closed ") and "OPPORTUNITY_CLOSE" not in u["permissions"]: raise HTTPException(403,"Opportunity-close permission required")
    validate_outcome(status,merged)
    vals={k:d[k] for k in ("owner_id","presales_owner_id","name","service_practice","status","forecast_category","amount","currency","probability","expected_close_date","proposal_date","last_follow_up_date","next_follow_up_date","final_amount","lost_reason","hold_reason","hold_review_date","competitor","remarks") if k in d}
    amount=float(vals.get("amount",old["amount"]) or 0); prob=float(vals.get("probability",old["probability"]) or 0); vals["weighted_value"]=amount*prob/100
    if "forecast_category" not in d and "status" in d: vals["forecast_category"]=forecast_from_status(status)
    vals["closed_at"]=today_str() if status.startswith("Closed ") else None; vals["updated_at"]=utcnow(); execute(update(opportunities).where(opportunities.c.id==opp_id).values(**vals))
    if d.get("presales_owner_id"):
        pid=int(d["presales_owner_id"])
        if not row(select(opportunity_team.c.opportunity_id).where(and_(opportunity_team.c.opportunity_id==opp_id,opportunity_team.c.user_id==pid))): execute(insert(opportunity_team).values(opportunity_id=opp_id,user_id=pid,team_role="Presales Owner",created_by=u["id"]))
    audit(u["id"],"opportunity",opp_id,"UPDATE",d); return opportunity_detail(opp_id,u)

@app.post("/api/opportunities/{opp_id}/followups")
def add_followup(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    d=p.data; fd=d.get("follow_up_date") or today_str(); oid=int(d.get("owner_id") or u["id"])
    fid=execute(insert(followups).values(opportunity_id=opp_id,follow_up_date=fd,owner_id=oid,response=d.get("response"),next_follow_up_date=d.get("next_follow_up_date"),remarks=d.get("remarks"),created_by=u["id"]))
    old=row(select(opportunities.c.follow_up_count).where(opportunities.c.id==opp_id)); execute(update(opportunities).where(opportunities.c.id==opp_id).values(last_follow_up_date=fd,next_follow_up_date=d.get("next_follow_up_date"),follow_up_count=(old["follow_up_count"] or 0)+1,updated_at=utcnow())); audit(u["id"],"followup",fid,"CREATE",d); return opportunity_detail(opp_id,u)

@app.post("/api/opportunities/{opp_id}/team")
def add_team_member(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    uid=int(p.data["user_id"]); role=p.data.get("team_role") or "Contributor"
    if not can_assign(u,uid): raise HTTPException(403,"You cannot add that user to this opportunity team")
    with engine.begin() as c:
        ex=c.execute(select(opportunity_team.c.opportunity_id).where(and_(opportunity_team.c.opportunity_id==opp_id,opportunity_team.c.user_id==uid))).fetchone()
        if ex: c.execute(update(opportunity_team).where(and_(opportunity_team.c.opportunity_id==opp_id,opportunity_team.c.user_id==uid)).values(team_role=role))
        else: c.execute(insert(opportunity_team).values(opportunity_id=opp_id,user_id=uid,team_role=role,created_by=u["id"]))
    audit(u["id"],"opportunity",opp_id,"TEAM_UPDATE",p.data); return opportunity_detail(opp_id,u)

@app.post("/api/documents")
def add_document(p:Payload,u=Depends(require_csrf)):
    if "DOCUMENT_EDIT" not in u["permissions"]: raise HTTPException(403,"Document permission required")
    d=p.data
    if not d.get("entity_type") or not d.get("entity_id") or not d.get("name") or not d.get("url"): raise HTTPException(400,"Entity, document name and approved repository URL are required")
    if d["entity_type"]=="lead" and not can_view_lead(u,int(d["entity_id"])): raise HTTPException(403,"Lead access denied")
    if d["entity_type"]=="opportunity" and not can_view_opp(u,int(d["entity_id"])): raise HTTPException(403,"Opportunity access denied")
    did=execute(insert(documents).values(entity_type=d["entity_type"],entity_id=int(d["entity_id"]),name=d["name"],document_type=d.get("document_type"),url=d["url"],version=d.get("version"),description=d.get("description"),uploaded_by=u["id"])); audit(u["id"],"document",did,"CREATE",d); return row(select(documents).where(documents.c.id==did))

@app.get("/api/targets")
def get_targets(year:int=Query(default=date.today().year),quarter:str=Query(default=q_current()),u=Depends(require_perm("FORECAST_VIEW"))):
    visible=scope_user_ids(u)
    return rows(select(targets.c.id,targets.c.user_id,users.c.name.label("user_name"),targets.c.year,targets.c.quarter,targets.c.currency,targets.c.target_amount).select_from(targets.join(users,users.c.id==targets.c.user_id)).where(and_(targets.c.year==year,targets.c.quarter==quarter,targets.c.user_id.in_(visible))).order_by(users.c.name))

@app.post("/api/targets")
def upsert_target(p:Payload,u=Depends(require_csrf)):
    if "TARGET_EDIT" not in u["permissions"]: raise HTTPException(403,"Target edit permission required")
    d=p.data; uid=int(d["user_id"]); year=int(d.get("year") or date.today().year); quarter=d.get("quarter") or q_current(); amount=float(d.get("target_amount") or 0)
    if uid not in scope_user_ids(u): raise HTTPException(403,"You can only set targets for users in your hierarchy")
    ex=row(select(targets.c.id).where(and_(targets.c.user_id==uid,targets.c.year==year,targets.c.quarter==quarter)))
    if ex: execute(update(targets).where(targets.c.id==ex["id"]).values(target_amount=amount,currency=d.get("currency") or "USD",updated_at=utcnow())); tid=ex["id"]
    else: tid=execute(insert(targets).values(user_id=uid,year=year,quarter=quarter,currency=d.get("currency") or "USD",target_amount=amount,created_by=u["id"]))
    audit(u["id"],"target",tid,"UPSERT",d); return {"ok":True,"id":tid}

def quarter_range(year:int,q:str):
    n=int(q[1]); sm=1+(n-1)*3; start=date(year,sm,1); end=date(year+1,1,1) if sm==10 else date(year,sm+3,1); return start,end

@app.get("/api/forecast/summary")
def forecast_summary(year:int=Query(default=date.today().year),quarter:str=Query(default=q_current()),u=Depends(require_perm("FORECAST_VIEW"))):
    start,end=quarter_range(year,quarter); visible=scope_user_ids(u); os_=opportunity_rows(u); data=[]; rates=fx_map(); corp=corporate_currency(); missing=set()
    def cv(v,c):
        x=to_corporate(v,c,rates)
        if x is None: missing.add(c or corp); return 0.0
        return x
    for uid in visible:
        su=safe_user(uid)
        if not su or su["role"] in {"Super Admin","Admin","Director","Presales Lead"}: continue
        mine_open=[o for o in os_ if o["owner_id"]==uid and not str(o.get("status") or "").startswith("Closed ") and o.get("expected_close_date") and start.isoformat()<=o["expected_close_date"]<end.isoformat()]
        mine_won=[o for o in os_ if o["owner_id"]==uid and o.get("status")=="Closed Won" and o.get("closed_at") and start.isoformat()<=o["closed_at"]<end.isoformat()]
        target=row(select(targets.c.target_amount,targets.c.currency).where(and_(targets.c.user_id==uid,targets.c.year==year,targets.c.quarter==quarter))) or {"target_amount":0,"currency":corp}
        pipeline=sum(cv(o.get("amount"),o.get("currency")) for o in mine_open if o.get("forecast_category")=="Pipeline")
        best=sum(cv(o.get("amount"),o.get("currency")) for o in mine_open if o.get("forecast_category")=="Best Case")
        commit=sum(cv(o.get("amount"),o.get("currency")) for o in mine_open if o.get("forecast_category")=="Commit")
        won=sum(cv(o.get("final_amount") or o.get("amount"),o.get("currency")) for o in mine_won)
        ta=cv(target["target_amount"],target["currency"]); data.append({"user_id":uid,"user_name":su["name"],"role":su["role"],"currency":corp,"target":round(ta,2),"target_original":float(target["target_amount"] or 0),"target_original_currency":target["currency"],"pipeline":round(pipeline,2),"best_case":round(best,2),"commit":round(commit,2),"closed_won":round(won,2),"achievement_pct":round(won/ta*100,1) if ta else 0})
    total={k:round(sum(float(x[k]) for x in data),2) for k in ("target","pipeline","best_case","commit","closed_won")}
    total["achievement_pct"]=round(total["closed_won"]/total["target"]*100,1) if total["target"] else 0
    return {"year":year,"quarter":quarter,"currency":corp,"rows":data,"total":total,"missing_fx_rates":sorted(missing),"fx_as_of":rows(select(fx_rates.c.currency,fx_rates.c.rate_to_corporate,fx_rates.c.as_of,fx_rates.c.source).order_by(fx_rates.c.currency))}

@app.get("/api/dashboard/summary")
def dashboard(u=Depends(current_user)):
    ls=lead_rows(u); os_=opportunity_rows(u); acts=list_actions("all",u); t=today_str(); rates=fx_map(); corp=corporate_currency(); won=[o for o in os_ if o["status"]=="Closed Won"]; lost=[o for o in os_ if o["status"]=="Closed Lost"]; active=[o for o in os_ if not o["status"].startswith("Closed ")]
    cv=lambda o,v=None: to_corporate(o.get(v or "amount") if v else o.get("amount"),o.get("currency"),rates) or 0
    fc={"Pipeline":0,"Best Case":0,"Commit":0,"Closed":0}
    for o in os_: fc[o.get("forecast_category") or forecast_from_status(o["status"])]=fc.get(o.get("forecast_category"),0)+cv(o)
    tg=forecast_summary(date.today().year,q_current(),u)["total"] if "FORECAST_VIEW" in u["permissions"] else {"target":0,"closed_won":0,"achievement_pct":0}
    return {"currency":corp,"scope":"All Business" if u["scope_type"]=="all" else ("My Team" if u["scope_type"]=="team" else "My Business"),"active_leads":len([l for l in ls if l["status"] not in ("Converted","Disqualified","Lost")]),"hot_leads":len([l for l in ls if l["temperature"]=="Hot"]),"active_opportunities":len(active),"pipeline_value":round(sum(cv(o) for o in active),2),"weighted_pipeline":round(sum((to_corporate(o.get("weighted_value"),o.get("currency"),rates) or 0) for o in active),2),"best_case":round(fc.get("Best Case",0),2),"commit":round(fc.get("Commit",0),2),"actions_due_today":len([a for a in acts if a["status"] not in ("Completed","Cancelled") and a["due_date"]==t]),"overdue_actions":len([a for a in acts if a.get("overdue")]),"followups_due":len([o for o in active if o.get("next_follow_up_date") and o["next_follow_up_date"]<=t]),"closed_won_value":round(sum(to_corporate(o.get("final_amount") or o.get("amount"),o.get("currency"),rates) or 0 for o in won),2),"closed_won_count":len(won),"closed_lost_count":len(lost),"win_rate":round(len(won)/(len(won)+len(lost))*100,1) if won or lost else 0,"target":tg.get("target",0),"achievement_pct":tg.get("achievement_pct",0)}

@app.get("/api/dashboard/pipeline")
def pipeline(u=Depends(current_user)):
    groups={}
    for o in opportunity_rows(u):
        g=groups.setdefault(o["status"],{"status":o["status"],"count":0,"value":0,"currency":corporate_currency()}); g["count"]+=1; g["value"]+=to_corporate(o.get("amount"),o.get("currency")) or 0
    return list(groups.values())

@app.get("/api/dashboard/attention")
def attention(u=Depends(current_user)):
    items=[]; t=date.today()
    for a in list_actions("all",u):
        if a.get("overdue"): items.append({"kind":"Overdue Action","company":a["company_name"],"subject":a["description"],"owner":a["assigned_to_name"],"date":a["due_date"],"severity":"Critical"})
    for o in opportunity_rows(u):
        if o["status"].startswith("Closed "): continue
        if o.get("next_follow_up_date") and o["next_follow_up_date"]<today_str(): items.append({"kind":"Follow-up Overdue","company":o["company_name"],"subject":o["name"],"owner":o["owner_name"],"date":o["next_follow_up_date"],"severity":"High"})
        if o.get("expected_close_date"):
            try:
                days=(date.fromisoformat(o["expected_close_date"])-t).days
                if 0<=days<=7: items.append({"kind":"Closure Approaching","company":o["company_name"],"subject":o["name"],"owner":o["owner_name"],"date":o["expected_close_date"],"severity":"High"})
            except: pass
    return items[:40]


@app.get("/api/dashboard/analytics")
def dashboard_analytics(u=Depends(current_user)):
    """Executive analytics for the JSAN-branded dashboard. Values honor the caller's record scope."""
    ls=lead_rows(u); os_=opportunity_rows(u); acts=list_actions("all",u); rates=fx_map(); corp=corporate_currency(); cv=lambda o,v="amount": to_corporate(o.get(v),o.get("currency"),rates) or 0
    # Prospect / lead health
    temp_order=["Hot","Warm","Cold"]
    temperature=[{"name":t,"count":sum(1 for l in ls if l.get("temperature")==t)} for t in temp_order]
    sources={}
    for l in ls:
        k=l.get("source") or "Other"; sources[k]=sources.get(k,0)+1
    source_mix=[{"name":k,"count":v} for k,v in sorted(sources.items(), key=lambda kv:kv[1], reverse=True)[:8]]
    regions={}
    for l in ls:
        k=l.get("region") or "Unassigned"; regions[k]=regions.get(k,0)+1
    region_mix=[{"name":k,"count":v} for k,v in sorted(regions.items(), key=lambda kv:kv[1], reverse=True)[:8]]

    # Pipeline and ageing
    stage_order=["New Opportunity","Qualified","Discussion","Presales / Solutioning","Proposal Submitted","Awaiting Response","Negotiation","Closed Won","Closed Lost","Closed Hold"]
    stage_map={}
    ageing={"0–30 days":0,"31–60 days":0,"61–90 days":0,"90+ days":0}
    for o in os_:
        g=stage_map.setdefault(o.get("status") or "Other", {"stage":o.get("status") or "Other","count":0,"value":0})
        g["count"]+=1; g["value"]+=cv(o)
        if not str(o.get("status") or "").startswith("Closed "):
            age=int(o.get("age_days") or 0)
            bucket="0–30 days" if age<=30 else "31–60 days" if age<=60 else "61–90 days" if age<=90 else "90+ days"
            ageing[bucket]+=1
    pipeline=[stage_map[x] for x in stage_order if x in stage_map] + [v for k,v in stage_map.items() if k not in stage_order]
    ageing_rows=[{"name":k,"count":v} for k,v in ageing.items()]

    # Owner performance
    owner={}
    for o in os_:
        name=o.get("owner_name") or "Unassigned"; r=owner.setdefault(name,{"owner":name,"pipeline":0,"won":0,"opportunities":0,"commit":0})
        r["opportunities"]+=1
        if not str(o.get("status") or "").startswith("Closed "): r["pipeline"]+=cv(o)
        if o.get("status")=="Closed Won": r["won"]+=to_corporate(o.get("final_amount") or o.get("amount"),o.get("currency"),rates) or 0
        if o.get("forecast_category")=="Commit": r["commit"]+=cv(o)
    owner_performance=sorted(owner.values(), key=lambda x:(x["pipeline"]+x["won"]), reverse=True)[:8]

    # Six-quarter trend using opportunity creation and actual close dates
    today=date.today(); current_q=((today.month-1)//3)+1
    periods=[]
    for offset in range(5,-1,-1):
        idx=(today.year*4 + (current_q-1))-offset; y=idx//4; q=idx%4+1; start,end=quarter_range(y,f"Q{q}")
        created=[o for o in os_ if o.get("created_at") and start.isoformat()<=str(o["created_at"])[:10]<end.isoformat()]
        won=[o for o in os_ if o.get("status")=="Closed Won" and o.get("closed_at") and start.isoformat()<=o["closed_at"]<end.isoformat()]
        periods.append({"period":f"Q{q} {str(y)[2:]}","pipeline":sum(cv(o) for o in created),"won":sum(to_corporate(o.get("final_amount") or o.get("amount"),o.get("currency"),rates) or 0 for o in won),"opportunities":len(created)})

    # Work execution
    action_status={}
    for a in acts:
        k="Overdue" if a.get("overdue") else (a.get("status") or "Other"); action_status[k]=action_status.get(k,0)+1
    action_mix=[{"name":k,"count":v} for k,v in action_status.items()]
    top_opps=[{"id":o["id"],"company":o["company_name"],"name":o["name"],"owner":o["owner_name"],"status":o["status"],"value":cv(o),"close_date":o.get("expected_close_date"),"forecast":o.get("forecast_category")} for o in sorted([x for x in os_ if not str(x.get("status") or "").startswith("Closed ")], key=lambda x:float(x.get("amount") or 0), reverse=True)[:6]]
    return {"currency":corp,"temperature":temperature,"source_mix":source_mix,"region_mix":region_mix,"pipeline":pipeline,"ageing":ageing_rows,"owner_performance":owner_performance,"quarter_trend":periods,"action_mix":action_mix,"top_opportunities":top_opps}

@app.get("/api/notifications")
def list_notifications(u=Depends(current_user)):
    run_workflows_for_user(u)
    return rows(select(notifications).where(and_(notifications.c.user_id==u["id"],notifications.c.read_at.is_(None))).order_by(notifications.c.id.desc()).limit(50))

def add_notice_once(user_id,typ,title,message,entity_type,entity_id,due,severity="warning"):
    ex=row(select(notifications.c.id).where(and_(notifications.c.user_id==user_id,notifications.c.notification_type==typ,notifications.c.entity_type==entity_type,notifications.c.entity_id==entity_id,notifications.c.due_date==due,notifications.c.read_at.is_(None))))
    if not ex: execute(insert(notifications).values(user_id=user_id,notification_type=typ,title=title,message=message,entity_type=entity_type,entity_id=entity_id,due_date=due,severity=severity))

def workflow_rule(code):
    r=row(select(workflow_rules.c.enabled,workflow_rules.c.config_json).where(workflow_rules.c.code==code))
    if not r or not r["enabled"]: return None
    try: cfg=json.loads(r.get("config_json") or "{}")
    except Exception: cfg={}
    return cfg

def run_workflows_for_user(u):
    t=date.today(); ts=t.isoformat()
    action_cfg=workflow_rule("ACTION_OVERDUE")
    if action_cfg is not None:
        for a in list_actions("all",u):
            if is_assignee(a,u["id"]) and a["status"] not in ("Completed","Cancelled") and a["due_date"]<=ts:
                add_notice_once(u["id"],"ACTION_DUE","Action overdue" if a["due_date"]<ts else "Action due today",f"{a['company_name']} · {a['description']}","action",a["id"],a["due_date"],"critical" if a["due_date"]<ts else "warning")
    response_cfg=workflow_rule("AWAITING_RESPONSE")
    close_cfg=workflow_rule("CLOSE_DATE")
    for o in opportunity_rows(u):
        if o["owner_id"]!=u["id"] or str(o["status"]).startswith("Closed "): continue
        if response_cfg is not None and o.get("next_follow_up_date") and o["next_follow_up_date"]<=ts:
            add_notice_once(u["id"],"FOLLOWUP_DUE","Opportunity follow-up due",f"{o['company_name']} · {o['name']}","opportunity",o["id"],o["next_follow_up_date"],"warning")
        if close_cfg is not None and o.get("expected_close_date"):
            try:
                days=(date.fromisoformat(o["expected_close_date"])-t).days; threshold=int(close_cfg.get("days",7))
                if 0<=days<=threshold: add_notice_once(u["id"],"CLOSE_DATE","Expected close approaching",f"{o['company_name']} · {o['name']}","opportunity",o["id"],o["expected_close_date"],"warning")
            except Exception: pass
    hot_cfg=workflow_rule("HOT_LEAD_INACTIVITY")
    if hot_cfg is not None:
        threshold=int(hot_cfg.get("days",7))
        for l in lead_rows(u):
            if l.get("owner_id")!=u["id"] or l.get("temperature")!="Hot": continue
            try:
                updated=l.get("updated_at"); dt=updated.date() if hasattr(updated,"date") else date.fromisoformat(str(updated)[:10])
                if (t-dt).days>=threshold: add_notice_once(u["id"],"HOT_LEAD_IDLE","Hot lead needs attention",f"{l['company_name']} · no recent activity","lead",l["id"],ts,"warning")
            except Exception: pass

@app.post("/api/notifications/{notification_id}/read")
def mark_notification(notification_id:int,u=Depends(require_csrf)):
    execute(update(notifications).where(and_(notifications.c.id==notification_id,notifications.c.user_id==u["id"])).values(read_at=utcnow())); return {"ok":True}

@app.get("/api/search")
def global_search(q:str=Query(min_length=2),u=Depends(current_user)):
    needle=q.lower(); results=[]
    if "COMPANY_VIEW" in u["permissions"]:
        for c in rows(select(companies).where(companies.c.status!="Merged")):
            if needle in (c["name"] or "").lower() or needle in (c.get("website") or "").lower(): results.append({"type":"Company","id":c["id"],"title":c["name"],"subtitle":c["vertical"]})
        for ct in rows(select(contacts,companies.c.name.label("company_name")).select_from(contacts.join(companies,companies.c.id==contacts.c.company_id)).where(contacts.c.active==True)):
            if can_access_company_relationship(u,int(ct["company_id"])) and any(needle in (str(ct.get(k) or "")).lower() for k in ("name","email","phone","designation")): results.append({"type":"Contact","id":ct["id"],"company_id":ct["company_id"],"title":ct["name"],"subtitle":ct["company_name"]})
    for l in lead_rows(u):
        if needle in l["company_name"].lower() or needle in (l.get("remarks") or "").lower(): results.append({"type":"Lead","id":l["id"],"title":l["company_name"],"subtitle":f"{l['temperature']} · {l['status']} · {l['owner_name']}"})
    for o in opportunity_rows(u):
        if needle in o["name"].lower() or needle in o["company_name"].lower(): results.append({"type":"Opportunity","id":o["id"],"title":o["name"],"subtitle":f"{o['company_name']} · {o['status']}"})
    return results[:50]

@app.get("/api/reports/period")
def period_report(year:int=Query(default=date.today().year),period:str=Query(default="Q1"),region:str=Query(default=""),u=Depends(require_perm("REPORT_VIEW"))):
    p=period.upper()
    if p not in {"Q1","Q2","Q3","Q4","H1","H2"}: raise HTTPException(400,"Period must be Q1-Q4, H1 or H2")
    if p.startswith("Q"): start,end=quarter_range(year,p)
    elif p=="H1": start,end=date(year,1,1),date(year,7,1)
    else: start,end=date(year,7,1),date(year+1,1,1)
    ls=lead_rows(u); os_=opportunity_rows(u); rates=fx_map(); corp=corporate_currency(); missing=set()
    if region:
        lead_ids_in_region={x["id"] for x in ls if (x.get("region") or "").lower()==region.lower()}
        ls=[x for x in ls if x["id"] in lead_ids_in_region]
        os_=[x for x in os_ if x.get("lead_id") in lead_ids_in_region]
    # Collect all unique regions for the dropdown
    all_regions=sorted({x.get("region") or "Unassigned" for x in lead_rows(u)})
    def cv(v,c):
        x=to_corporate(v,c,rates)
        if x is None: missing.add(c or corp); return 0.0
        return x
    lp=[x for x in ls if start.isoformat()<=str(x["created_at"])[:10]<end.isoformat()]
    op=[x for x in os_ if start.isoformat()<=str(x["created_at"])[:10]<end.isoformat()]
    closed=[x for x in os_ if x.get("closed_at") and start.isoformat()<=x["closed_at"]<end.isoformat()]
    won=[x for x in closed if x["status"]=="Closed Won"]; lost=[x for x in closed if x["status"]=="Closed Lost"]
    # A record's vertical can carry multiple comma-separated tags (no cap on how many), so it
    # is attributed to every tag it carries rather than one bucket keyed by the raw string.
    def vtags(v): return split_verticals(v) or ["Other"]
    verticals={}; sources={}; owners={}
    for l in lp:
        for v in vtags(l["vertical"]): verticals.setdefault(v,{"vertical":v,"leads":0,"pipeline":0,"won":0})["leads"]+=1
        sources.setdefault(l["source"],{"source":l["source"],"leads":0,"opportunities":0,"won":0})["leads"]+=1
    lmap={x["id"]:x for x in ls}
    for o in op:
        for v in vtags(o["vertical"]): verticals.setdefault(v,{"vertical":v,"leads":0,"pipeline":0,"won":0})["pipeline"]+=cv(o.get("amount"),o.get("currency"))
        src=lmap.get(o["lead_id"],{}).get("source","Other"); sources.setdefault(src,{"source":src,"leads":0,"opportunities":0,"won":0})["opportunities"]+=1
        owners.setdefault(o["owner_name"],{"owner":o["owner_name"],"opportunities":0,"pipeline":0,"won":0}); owners[o["owner_name"]]["opportunities"]+=1; owners[o["owner_name"]]["pipeline"]+=cv(o.get("amount"),o.get("currency"))
    for o in won:
        value=cv(o.get("final_amount") or o.get("amount"),o.get("currency"))
        for v in vtags(o["vertical"]): verticals.setdefault(v,{"vertical":v,"leads":0,"pipeline":0,"won":0})["won"]+=value
        src=lmap.get(o["lead_id"],{}).get("source","Other"); sources.setdefault(src,{"source":src,"leads":0,"opportunities":0,"won":0})["won"]+=1
        owners.setdefault(o["owner_name"],{"owner":o["owner_name"],"opportunities":0,"pipeline":0,"won":0})["won"]+=value
    # Geographic aggregation for map
    region_counts={}
    for l in lp:
        rn=(l.get("region") or "").strip() or "Unassigned"
        region_counts[rn]=region_counts.get(rn,0)+1
    locations={}
    for l in lp:
        c=l.get("country") or l.get("region") or "Unknown"
        if c and c!="Unknown":
            locations.setdefault(c,{"country":c,"region":l.get("region",""),"leads":0,"opportunities":0,"pipeline":0})["leads"]+=1
    for o in op:
        ll=lmap.get(o["lead_id"],{})
        c=ll.get("country") or ll.get("region") or o.get("vertical") or "Unknown"
        if c and c!="Unknown":
            locations.setdefault(c,{"country":c,"region":ll.get("region",""),"leads":0,"opportunities":0,"pipeline":0})
            locations[c]["opportunities"]+=1
            locations[c]["pipeline"]+=cv(o.get("amount"),o.get("currency"))
    return {"period":p,"year":year,"region":region,"regions":all_regions,"currency":corp,"missing_fx_rates":sorted(missing),"summary":{"leads_created":len(lp),"opportunities_created":len(op),"pipeline_created":round(sum(cv(x.get("amount"),x.get("currency")) for x in op),2),"closed_won_count":len(won),"closed_won_value":round(sum(cv(x.get("final_amount") or x.get("amount"),x.get("currency")) for x in won),2),"closed_lost_count":len(lost),"win_rate":round(len(won)/(len(won)+len(lost))*100,1) if won or lost else 0},"verticals":sorted(verticals.values(),key=lambda x:x["pipeline"],reverse=True),"sources":sorted(sources.values(),key=lambda x:x["leads"],reverse=True),"owners":sorted(owners.values(),key=lambda x:x["pipeline"],reverse=True),"locations":sorted(locations.values(),key=lambda x:x["leads"],reverse=True),"region_counts":[{"region":k,"leads":v} for k,v in sorted(region_counts.items(),key=lambda kv:(-kv[1],kv[0]=="Unassigned",kv[0].lower()))]}

@app.get("/api/admin/master-values")
def get_masters(u=Depends(current_user)): return rows(select(master_values).where(master_values.c.active==True).order_by(master_values.c.category,master_values.c.sort_order))

@app.get("/api/admin/workflows")
def get_workflows(u=Depends(require_perm("WORKFLOW_ADMIN"))): return rows(select(workflow_rules).order_by(workflow_rules.c.id))

@app.put("/api/admin/workflows/{rule_id}")
def update_workflow(rule_id:int,p:Payload,u=Depends(require_csrf)):
    if "WORKFLOW_ADMIN" not in u["permissions"]: raise HTTPException(403,"Workflow administration permission required")
    d=p.data; vals={k:d[k] for k in ("name","description","enabled","config_json") if k in d}; vals["updated_at"]=utcnow(); execute(update(workflow_rules).where(workflow_rules.c.id==rule_id).values(**vals)); audit(u["id"],"workflow",rule_id,"UPDATE",d); return row(select(workflow_rules).where(workflow_rules.c.id==rule_id))

def log_user_scope(u):
    """Audit trails follow the hierarchy: Super Admins see every entry, others only their own and their reports'."""
    return None if is_super(u) else [u["id"]]+descendants(u["id"],include_inactive=True)

@app.get("/api/audit-logs")
def get_audit(u=Depends(require_perm("AUDIT_VIEW"))):
    stmt=select(audit_logs.c.id,audit_logs.c.user_id,users.c.name.label("user_name"),audit_logs.c.entity_type,audit_logs.c.entity_id,audit_logs.c.action,audit_logs.c.details,audit_logs.c.created_at).select_from(audit_logs.outerjoin(users,users.c.id==audit_logs.c.user_id))
    ids=log_user_scope(u)
    if ids is not None: stmt=stmt.where(audit_logs.c.user_id.in_(ids))
    return rows(stmt.order_by(audit_logs.c.id.desc()).limit(300))

@app.get("/api/security-logs")
def get_security_logs(u=Depends(require_perm("AUDIT_VIEW"))):
    stmt=select(security_logs.c.id,security_logs.c.user_id,users.c.name.label("user_name"),security_logs.c.event_type,security_logs.c.success,security_logs.c.ip_address,security_logs.c.details,security_logs.c.created_at).select_from(security_logs.outerjoin(users,users.c.id==security_logs.c.user_id))
    ids=log_user_scope(u)
    if ids is not None: stmt=stmt.where(security_logs.c.user_id.in_(ids))
    return rows(stmt.order_by(security_logs.c.id.desc()).limit(300))

@app.get("/api/admin/field-permissions")
def get_field_permissions(u=Depends(require_perm("ROLE_ADMIN"))):
    return rows(select(field_permissions.c.role_id,roles.c.name.label("role"),field_permissions.c.entity_type,field_permissions.c.field_name,field_permissions.c.can_view,field_permissions.c.can_edit).select_from(field_permissions.join(roles,roles.c.id==field_permissions.c.role_id)).order_by(roles.c.rank,field_permissions.c.entity_type,field_permissions.c.field_name))

@app.put("/api/admin/field-permissions")
def update_field_permission(p:Payload,u=Depends(require_csrf)):
    if "ROLE_ADMIN" not in u["permissions"]: raise HTTPException(403,"Role administration permission required")
    d=p.data; rid=int(d["role_id"]); entity=d["entity_type"]; field=d["field_name"]
    ex=row(select(field_permissions.c.role_id).where(and_(field_permissions.c.role_id==rid,field_permissions.c.entity_type==entity,field_permissions.c.field_name==field)))
    vals={"can_view":bool(d.get("can_view",True)),"can_edit":bool(d.get("can_edit",True))}
    if ex: execute(update(field_permissions).where(and_(field_permissions.c.role_id==rid,field_permissions.c.entity_type==entity,field_permissions.c.field_name==field)).values(**vals))
    else: execute(insert(field_permissions).values(role_id=rid,entity_type=entity,field_name=field,**vals))
    audit(u["id"],"field_permission",rid,"UPSERT",d); return {"ok":True}

@app.get("/api/admin/currency")
def currency_settings(u=Depends(require_perm("FORECAST_VIEW"))):
    corp=corporate_currency(); rates=rows(select(fx_rates).order_by(fx_rates.c.currency))
    return {"corporate_currency":corp,"rates":rates,"warning":"Rates marked DEMO-SEED must be replaced with approved treasury/finance rates before production use."}

@app.put("/api/admin/currency")
def update_currency_settings(p:Payload,u=Depends(require_csrf)):
    if "TARGET_EDIT" not in u["permissions"] and "ROLE_ADMIN" not in u["permissions"]: raise HTTPException(403,"Forecast administration permission required")
    d=p.data; corp=(d.get("corporate_currency") or corporate_currency()).upper(); rates=d.get("rates") or []
    ex=row(select(org_settings.c.id).where(org_settings.c.key=="corporate_currency"))
    if ex: execute(update(org_settings).where(org_settings.c.id==ex["id"]).values(value=corp,updated_by=u["id"],updated_at=utcnow()))
    else: execute(insert(org_settings).values(key="corporate_currency",value=corp,updated_by=u["id"]))
    for rr in rates:
        cur=str(rr["currency"]).upper(); rate=float(rr["rate_to_corporate"])
        if rate<=0: raise HTTPException(400,"FX rates must be positive")
        exr=row(select(fx_rates.c.id).where(fx_rates.c.currency==cur)); vals={"rate_to_corporate":rate,"as_of":rr.get("as_of") or today_str(),"source":rr.get("source") or "MANUAL","updated_by":u["id"],"updated_at":utcnow()}
        if exr: execute(update(fx_rates).where(fx_rates.c.id==exr["id"]).values(**vals))
        else: execute(insert(fx_rates).values(currency=cur,**vals))
    # enforce corporate base at 1
    base=row(select(fx_rates.c.id).where(fx_rates.c.currency==corp))
    if base: execute(update(fx_rates).where(fx_rates.c.id==base["id"]).values(rate_to_corporate=1.0,updated_by=u["id"],updated_at=utcnow()))
    else: execute(insert(fx_rates).values(currency=corp,rate_to_corporate=1.0,as_of=today_str(),source="CORPORATE-BASE",updated_by=u["id"]))
    audit(u["id"],"currency",None,"UPDATE",d); return currency_settings(u)

@app.get("/api/saved-views")
def list_saved_views(module:str|None=None,u=Depends(current_user)):
    stmt=select(saved_views).where(saved_views.c.user_id==u["id"])
    if module: stmt=stmt.where(saved_views.c.module==module)
    return rows(stmt.order_by(saved_views.c.module,saved_views.c.name))

@app.post("/api/saved-views")
def save_view(p:Payload,u=Depends(require_csrf)):
    d=p.data
    if not d.get("module") or not d.get("name"): raise HTTPException(400,"Module and view name are required")
    if d.get("is_default"): execute(update(saved_views).where(and_(saved_views.c.user_id==u["id"],saved_views.c.module==d["module"])).values(is_default=False,updated_at=utcnow()))
    ex=row(select(saved_views.c.id).where(and_(saved_views.c.user_id==u["id"],saved_views.c.module==d["module"],saved_views.c.name==d["name"])))
    vals={"filters_json":json.dumps(d.get("filters") or {}),"columns_json":json.dumps(d.get("columns") or []),"is_default":bool(d.get("is_default")),"updated_at":utcnow()}
    if ex: execute(update(saved_views).where(saved_views.c.id==ex["id"]).values(**vals)); vid=ex["id"]
    else: vid=execute(insert(saved_views).values(user_id=u["id"],module=d["module"],name=d["name"],**vals))
    return row(select(saved_views).where(saved_views.c.id==vid))

@app.delete("/api/saved-views/{view_id}")
def delete_saved_view(view_id:int,u=Depends(require_csrf)):
    execute(delete(saved_views).where(and_(saved_views.c.id==view_id,saved_views.c.user_id==u["id"]))); return {"ok":True}

@app.get("/api/dashboard/preferences")
def get_dashboard_preferences(u=Depends(current_user)):
    r=row(select(dashboard_preferences).where(dashboard_preferences.c.user_id==u["id"]))
    return r or {"user_id":u["id"],"widgets_json":"[]","layout_json":"{}"}

@app.put("/api/dashboard/preferences")
def set_dashboard_preferences(p:Payload,u=Depends(require_csrf)):
    d=p.data; vals={"widgets_json":json.dumps(d.get("widgets") or []),"layout_json":json.dumps(d.get("layout") or {}),"updated_at":utcnow()}
    ex=row(select(dashboard_preferences.c.user_id).where(dashboard_preferences.c.user_id==u["id"]))
    if ex: execute(update(dashboard_preferences).where(dashboard_preferences.c.user_id==u["id"]).values(**vals))
    else: execute(insert(dashboard_preferences).values(user_id=u["id"],**vals))
    return {"ok":True}

def lead_visibility_condition(u):
    owner_ids=scope_user_ids(u)
    conds=[leads.c.owner_id.in_(owner_ids)]
    shared=select(record_shares.c.entity_id).where(and_(record_shares.c.entity_type=="Lead",record_shares.c.user_id==u["id"]))
    conds.append(leads.c.id.in_(shared))
    conds.append(leads.c.id.in_(select(record_people.c.entity_id).where(and_(record_people.c.entity_type=="lead",record_people.c.user_id.in_(owner_ids)))))
    return or_(*conds)

def opportunity_visibility_condition(u):
    owner_ids=scope_user_ids(u)
    conds=[opportunities.c.owner_id.in_(owner_ids)]
    team=select(opportunity_team.c.opportunity_id).where(opportunity_team.c.user_id==u["id"])
    shared=select(record_shares.c.entity_id).where(and_(record_shares.c.entity_type=="Opportunity",record_shares.c.user_id==u["id"]))
    conds.extend([opportunities.c.id.in_(team),opportunities.c.id.in_(shared)])
    return or_(*conds)

@app.get("/api/query/companies")
def query_companies(q:str="",vertical:str="",region:str="",page:int=1,page_size:int=25,u=Depends(require_perm("COMPANY_VIEW"))):
    page=max(1,page); page_size=min(max(1,page_size),100)
    contact_count=select(func.count(contacts.c.id)).where(and_(contacts.c.company_id==companies.c.id,contacts.c.active==True)).correlate(companies).scalar_subquery()
    lead_count=select(func.count(leads.c.id)).where(leads.c.company_id==companies.c.id).correlate(companies).scalar_subquery()
    opp_count=select(func.count(opportunities.c.id)).where(opportunities.c.company_id==companies.c.id).correlate(companies).scalar_subquery()
    stmt=select(companies,contact_count.label("contact_count"),lead_count.label("lead_count"),opp_count.label("opportunity_count")).where(companies.c.status!="Merged")
    filters=[]
    if q: filters.append(or_(func.lower(companies.c.name).like(f"%{q.lower()}%"),func.lower(func.coalesce(companies.c.website," ")).like(f"%{q.lower()}%"),func.lower(func.coalesce(companies.c.vertical," ")).like(f"%{q.lower()}%")))
    if vertical: filters.append(func.lower(companies.c.vertical).like(f"%{vertical.lower()}%"))
    if region: filters.append(companies.c.region==region)
    if filters: stmt=stmt.where(*filters)
    total_stmt=select(func.count()).select_from(select(companies.c.id).where(companies.c.status!="Merged",*filters).subquery())
    n=row(total_stmt); n=list(n.values())[0] if n else 0
    totals=row(select(func.count(companies.c.id.distinct()).label("companies"),func.count(contacts.c.id.distinct()).label("contacts"),func.count(leads.c.id.distinct()).label("leads"),func.count(opportunities.c.id.distinct()).label("opportunities")).select_from(companies.outerjoin(contacts,and_(contacts.c.company_id==companies.c.id,contacts.c.active==True)).outerjoin(leads,leads.c.company_id==companies.c.id).outerjoin(opportunities,opportunities.c.company_id==companies.c.id)).where(companies.c.status!="Merged")) or {}
    items=rows(stmt.order_by(companies.c.name).offset((page-1)*page_size).limit(page_size))
    return {"items":items,"page":page,"page_size":page_size,"total":n,"pages":(n+page_size-1)//page_size,"summary":totals}

@app.get("/api/query/leads")
def query_leads(q:str="",status:str="",temperature:str="",owner_id:int|None=None,region:str="",followup:str="",sort:str="",dir:str="asc",page:int=1,page_size:int=25,u=Depends(require_perm("LEAD_VIEW"))):
    page=max(1,page); page_size=min(max(1,page_size),100); owner=users.alias("owner")
    primary=select(contacts.c.name).where(and_(contacts.c.company_id==leads.c.company_id,contacts.c.active==True)).order_by(contacts.c.is_primary.desc(),contacts.c.id).limit(1).correlate(leads).scalar_subquery()
    joined=leads.join(companies,companies.c.id==leads.c.company_id).join(owner,owner.c.id==leads.c.owner_id)
    base=select(leads,companies.c.name.label("company_name"),companies.c.vertical,owner.c.name.label("owner_name"),primary.label("primary_contact")).select_from(joined).where(lead_visibility_condition(u))
    common=[]
    if q: common.append(or_(func.lower(companies.c.name).like(f"%{q.lower()}%"),func.lower(func.coalesce(leads.c.remarks," ")).like(f"%{q.lower()}%"),func.lower(owner.c.name).like(f"%{q.lower()}%"),leads.c.id.in_(select(record_people.c.entity_id).select_from(record_people.join(users,users.c.id==record_people.c.user_id)).where(and_(record_people.c.entity_type=="lead",func.lower(users.c.name).like(f"%{q.lower()}%"))))))
    if status: common.append(leads.c.status==status)
    if owner_id: common.append(or_(leads.c.owner_id==owner_id,leads.c.id.in_(select(record_people.c.entity_id).where(and_(record_people.c.entity_type=="lead",record_people.c.user_id==owner_id)))))
    if region=="__none__": common.append(or_(leads.c.region.is_(None),leads.c.region==""))
    elif region: common.append(leads.c.region==region)
    t=today_str(); week=(date.today()+timedelta(days=7)).isoformat()
    if followup=="overdue": common.append(and_(leads.c.next_follow_up.is_not(None),leads.c.next_follow_up!="",leads.c.next_follow_up<t))
    elif followup=="today": common.append(leads.c.next_follow_up==t)
    elif followup=="week": common.append(and_(leads.c.next_follow_up>=t,leads.c.next_follow_up<=week))
    elif followup=="none": common.append(or_(leads.c.next_follow_up.is_(None),leads.c.next_follow_up==""))
    elif followup: common.append(leads.c.next_follow_up==followup)  # an exact date picked from the column's values
    # Filter options are the distinct values actually present in every visible lead, so menus don't shrink as filters apply
    facet_rows=rows(select(leads.c.region,leads.c.owner_id,owner.c.name.label("owner_name"),leads.c.temperature,leads.c.status,leads.c.next_follow_up).select_from(joined).where(lead_visibility_condition(u)).distinct())
    distinct=lambda k:{r[k] for r in facet_rows if r[k]}
    temp_order={"Hot":0,"Warm":1,"Cold":2}
    facets={"temperatures":sorted(distinct("temperature"),key=lambda v:(temp_order.get(v,9),v)),
            "statuses":sorted(distinct("status"),key=str.lower),
            "follow_ups":sorted(distinct("next_follow_up")),
            "has_empty_follow_up":any(not r["next_follow_up"] for r in facet_rows),
            "regions":sorted(distinct("region"),key=str.lower),
            "has_empty_region":any(not r["region"] for r in facet_rows),
            "owners":sorted([{"id":oid,"name":n} for oid,n in {(r["owner_id"],r["owner_name"]) for r in facet_rows}|{(r["user_id"],r["name"]) for r in rows(select(record_people.c.user_id,users.c.name).select_from(record_people.join(users,users.c.id==record_people.c.user_id)).where(and_(record_people.c.entity_type=="lead",record_people.c.entity_id.in_(select(leads.c.id).where(lead_visibility_condition(u))))).distinct())}],key=lambda x:(x["name"] or "").lower())}
    if common: base=base.where(*common)
    summary_stmt=select(leads.c.temperature,func.count(leads.c.id).label("count")).select_from(leads.join(companies,companies.c.id==leads.c.company_id).join(owner,owner.c.id==leads.c.owner_id)).where(lead_visibility_condition(u),*common).group_by(leads.c.temperature)
    temp_counts={r["temperature"]:r["count"] for r in rows(summary_stmt)}
    overdue_stmt=select(func.count(leads.c.id).label("count")).select_from(leads.join(companies,companies.c.id==leads.c.company_id).join(owner,owner.c.id==leads.c.owner_id)).where(lead_visibility_condition(u),*common,leads.c.next_follow_up.is_not(None),leads.c.next_follow_up<today_str(),~leads.c.status.in_(["Converted","Disqualified","Lost"]))
    overdue=(row(overdue_stmt) or {}).get("count",0)
    if temperature: base=base.where(leads.c.temperature==temperature)
    nrow=row(select(func.count().label("total")).select_from(base.subquery())); n=int((nrow or {}).get("total",0))
    # Whitelisted sort keys only; never pass user input into ORDER BY
    temp_rank=case((leads.c.temperature=="Hot",0),(leads.c.temperature=="Warm",1),(leads.c.temperature=="Cold",2),else_=3)
    sort_cols={"company_name":func.lower(companies.c.name),"temperature":temp_rank,"status":func.lower(leads.c.status),
               "owner_name":func.lower(owner.c.name),"next_follow_up":leads.c.next_follow_up,"region":func.lower(func.coalesce(leads.c.region,""))}
    order=[]
    if sort in sort_cols:
        col=sort_cols[sort]
        if sort in ("next_follow_up","region"):  # empty values always last
            empty=or_(leads.c.next_follow_up.is_(None),leads.c.next_follow_up=="") if sort=="next_follow_up" else or_(leads.c.region.is_(None),leads.c.region=="")
            order.append(case((empty,1),else_=0))
        order.append(col.desc() if dir=="desc" else col.asc())
    order.append(leads.c.updated_at.desc())
    items=rows(base.order_by(*order).offset((page-1)*page_size).limit(page_size))
    if "LEAD_EDIT" in u["permissions"] and items:
        scope=set(scope_user_ids(u))
        shared_edit={r["entity_id"] for r in rows(select(record_shares.c.entity_id).where(and_(record_shares.c.entity_type=="lead",record_shares.c.user_id==u["id"],record_shares.c.access_level=="edit",record_shares.c.entity_id.in_([i["id"] for i in items]))))}
        co=people_map("lead",[i["id"] for i in items])
        for i in items:
            i["co_owners"]=co.get(i["id"],[])
            i["can_edit"]=i["owner_id"] in scope or i["id"] in shared_edit or any(p["id"] in scope for p in i["co_owners"])
    else:
        co=people_map("lead",[i["id"] for i in items])
        for i in items: i["can_edit"]=False; i["co_owners"]=co.get(i["id"],[])
    return {"items":items,"page":page,"page_size":page_size,"total":n,"pages":(n+page_size-1)//page_size,"facets":facets,"summary":{"hot":temp_counts.get("Hot",0),"warm":temp_counts.get("Warm",0),"cold":temp_counts.get("Cold",0),"overdue_followups":overdue}}

@app.get("/api/query/opportunities")
def query_opportunities(q:str="",status:str="",forecast_category:str="",owner_id:int|None=None,page:int=1,page_size:int=25,u=Depends(require_perm("OPPORTUNITY_VIEW"))):
    page=max(1,page); page_size=min(max(1,page_size),100); owner=users.alias("owner")
    base=select(opportunities,companies.c.name.label("company_name"),companies.c.vertical,owner.c.name.label("owner_name")).select_from(opportunities.join(companies,companies.c.id==opportunities.c.company_id).join(owner,owner.c.id==opportunities.c.owner_id)).where(opportunity_visibility_condition(u))
    common=[]
    if q: common.append(or_(func.lower(opportunities.c.name).like(f"%{q.lower()}%"),func.lower(companies.c.name).like(f"%{q.lower()}%"),func.lower(owner.c.name).like(f"%{q.lower()}%")))
    if status: common.append(opportunities.c.status==status)
    if forecast_category: common.append(opportunities.c.forecast_category==forecast_category)
    if owner_id: common.append(opportunities.c.owner_id==owner_id)
    if common: base=base.where(*common)
    nrow=row(select(func.count().label("total")).select_from(base.subquery())); n=int((nrow or {}).get("total",0))
    raw=rows(base.order_by(opportunities.c.updated_at.desc()).offset((page-1)*page_size).limit(page_size)); items=[mask_fields(u,"opportunity",x) for x in raw]
    summary_rows=rows(select(opportunities.c.amount,opportunities.c.currency,opportunities.c.forecast_category,opportunities.c.status,opportunities.c.next_follow_up_date).select_from(opportunities.join(companies,companies.c.id==opportunities.c.company_id).join(owner,owner.c.id==opportunities.c.owner_id)).where(opportunity_visibility_condition(u),*common))
    rates=fx_map(); pipeline=best=commit=0.0; due=active=0
    for o in summary_rows:
        if str(o.get("status") or "").startswith("Closed "): continue
        active+=1; val=to_corporate(o.get("amount"),o.get("currency"),rates) or 0; pipeline+=val
        if o.get("forecast_category")=="Best Case": best+=val
        if o.get("forecast_category")=="Commit": commit+=val
        if o.get("next_follow_up_date") and o["next_follow_up_date"]<=today_str(): due+=1
    return {"items":items,"page":page,"page_size":page_size,"total":n,"pages":(n+page_size-1)//page_size,"currency":corporate_currency(),"summary":{"active":active,"pipeline":round(pipeline,2),"best_case":round(best,2),"commit":round(commit,2),"followups_due":due}}

@app.get("/api/integrations/microsoft/status")
def microsoft_status(u=Depends(current_user)):
    r=row(select(microsoft_integrations.c.connected_email,microsoft_integrations.c.connected_at,microsoft_integrations.c.updated_at).where(microsoft_integrations.c.user_id==u["id"]))
    return {"configured":bool(MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET),"connected":bool(r),"account":r}

@app.get("/api/integrations/microsoft/connect")
def microsoft_connect(u=Depends(current_user)):
    if not MICROSOFT_CLIENT_ID or not MICROSOFT_CLIENT_SECRET: raise HTTPException(503,"Microsoft 365 integration is not configured by the administrator")
    state=secrets.token_urlsafe(32); MS_OAUTH_STATE[state]=(u["id"],time.time()+600)
    params={"client_id":MICROSOFT_CLIENT_ID,"response_type":"code","redirect_uri":MICROSOFT_REDIRECT_URI,"response_mode":"query","scope":MICROSOFT_SCOPES,"state":state}
    return {"authorization_url":f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/authorize?{urlencode(params)}"}

@app.get("/api/integrations/microsoft/callback")
def microsoft_callback(code:str,state:str):
    st=MS_OAUTH_STATE.pop(state,None)
    if not st or st[1]<time.time(): raise HTTPException(400,"Invalid or expired Microsoft OAuth state")
    uid=st[0]
    token_url=f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data={"client_id":MICROSOFT_CLIENT_ID,"client_secret":MICROSOFT_CLIENT_SECRET,"code":code,"grant_type":"authorization_code","redirect_uri":MICROSOFT_REDIRECT_URI,"scope":MICROSOFT_SCOPES}
    with httpx.Client(timeout=20) as client:
        tr=client.post(token_url,data=data); tr.raise_for_status(); tok=tr.json(); access=tok["access_token"]; refresh=tok.get("refresh_token")
        me=client.get("https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName",headers={"Authorization":f"Bearer {access}"}); me.raise_for_status(); md=me.json(); email=md.get("mail") or md.get("userPrincipalName")
    vals={"tenant_id":MICROSOFT_TENANT_ID,"connected_email":email,"scope":tok.get("scope"),"encrypted_refresh_token":enc_token(refresh) if refresh else None,"connected_at":utcnow(),"updated_at":utcnow()}
    ex=row(select(microsoft_integrations.c.user_id).where(microsoft_integrations.c.user_id==uid))
    if ex: execute(update(microsoft_integrations).where(microsoft_integrations.c.user_id==uid).values(**vals))
    else: execute(insert(microsoft_integrations).values(user_id=uid,**vals))
    return RedirectResponse(url="/?microsoft=connected")

def ms_access_token(u):
    r=row(select(microsoft_integrations).where(microsoft_integrations.c.user_id==u["id"]))
    if not r or not r.get("encrypted_refresh_token"): raise HTTPException(409,"Connect Microsoft 365 first")
    token_url=f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"
    data={"client_id":MICROSOFT_CLIENT_ID,"client_secret":MICROSOFT_CLIENT_SECRET,"refresh_token":dec_token(r["encrypted_refresh_token"]),"grant_type":"refresh_token","scope":MICROSOFT_SCOPES}
    with httpx.Client(timeout=20) as client:
        tr=client.post(token_url,data=data); tr.raise_for_status(); tok=tr.json()
    if tok.get("refresh_token"): execute(update(microsoft_integrations).where(microsoft_integrations.c.user_id==u["id"]).values(encrypted_refresh_token=enc_token(tok["refresh_token"]),updated_at=utcnow()))
    return tok["access_token"]

@app.post("/api/integrations/microsoft/meetings/{meeting_id}/sync")
def sync_meeting_microsoft(meeting_id:int,u=Depends(require_csrf)):
    m=row(select(meetings,companies.c.name.label("company_name")).select_from(meetings.join(leads,leads.c.id==meetings.c.lead_id).join(companies,companies.c.id==leads.c.company_id)).where(meetings.c.id==meeting_id))
    if not m or not can_view_lead(u,m["lead_id"]): raise HTTPException(404,"Meeting not found")
    token=ms_access_token(u); start=f"{m['meeting_date']}T{m.get('meeting_time') or '10:00'}:00"; end_dt=(datetime.fromisoformat(start)+timedelta(minutes=60)).isoformat()
    payload={"subject":f"{m['company_name']} - {m['meeting_type']}","body":{"contentType":"HTML","content":m.get("purpose") or "PursuitNova customer meeting"},"start":{"dateTime":start,"timeZone":"UTC"},"end":{"dateTime":end_dt,"timeZone":"UTC"},"isOnlineMeeting":True,"onlineMeetingProvider":"teamsForBusiness"}
    with httpx.Client(timeout=20) as client:
        r=client.post("https://graph.microsoft.com/v1.0/me/events",json=payload,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}); r.raise_for_status(); event=r.json()
    audit(u["id"],"meeting",meeting_id,"MICROSOFT_SYNC",{"event_id":event.get("id"),"webLink":event.get("webLink")}); return {"event_id":event.get("id"),"web_link":event.get("webLink"),"teams_join_url":(event.get("onlineMeeting") or {}).get("joinUrl")}

@app.post("/api/integrations/microsoft/send-mail")
def microsoft_send_mail(p:Payload,u=Depends(require_csrf)):
    d=p.data
    if not d.get("to") or not d.get("subject"): raise HTTPException(400,"Recipient and subject are required")
    token=ms_access_token(u); payload={"message":{"subject":d["subject"],"body":{"contentType":"HTML","content":d.get("body") or ""},"toRecipients":[{"emailAddress":{"address":d["to"]}}]},"saveToSentItems":True}
    with httpx.Client(timeout=20) as client:
        r=client.post("https://graph.microsoft.com/v1.0/me/sendMail",json=payload,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"}); r.raise_for_status()
    audit(u["id"],"integration",None,"OUTLOOK_MAIL_SENT",{"to":d["to"],"subject":d["subject"]}); return {"ok":True}

@app.get("/healthz")
def healthz(): return {"status":"ok","product":APP_NAME,"version":APP_VERSION}

@app.get("/readyz")
def readyz():
    try:
        row(text("SELECT 1")); return {"status":"ready","database":engine.dialect.name}
    except Exception as e: raise HTTPException(503,"Database unavailable")

@app.get("/api/monitoring/metrics")
def monitoring_metrics(u=Depends(require_perm("AUDIT_VIEW"))):
    req=REQUEST_METRICS["requests"]; avg=REQUEST_METRICS["latency_ms_total"]/req if req else 0
    return {"product":APP_NAME,"version":APP_VERSION,"uptime_seconds":round(time.time()-REQUEST_METRICS["started_at"]),"requests":req,"errors":REQUEST_METRICS["errors"],"avg_latency_ms":round(avg,2),"database":engine.dialect.name}

@app.get("/metrics",response_class=PlainTextResponse)
def prometheus_metrics(request:Request):
    if METRICS_TOKEN and request.headers.get("X-Metrics-Token") != METRICS_TOKEN: raise HTTPException(401,"Metrics token required")
    req=REQUEST_METRICS["requests"]; avg=REQUEST_METRICS["latency_ms_total"]/req if req else 0
    return f"pursuitnova_requests_total {req}\npursuitnova_errors_total {REQUEST_METRICS['errors']}\npursuitnova_request_latency_ms_avg {avg:.3f}\n"

@app.get("/api/export/opportunities.csv")
def export_opportunities(u=Depends(require_perm("DATA_EXPORT"))):
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=["company","opportunity","owner","status","forecast_category","amount","currency","expected_close_date","next_follow_up_date"]); writer.writeheader()
    for o in opportunity_rows(u): writer.writerow({"company":o["company_name"],"opportunity":o["name"],"owner":o["owner_name"],"status":o["status"],"forecast_category":o["forecast_category"],"amount":o["amount"],"currency":o["currency"],"expected_close_date":o.get("expected_close_date"),"next_follow_up_date":o.get("next_follow_up_date")})
    return StreamingResponse(iter([out.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=pursuitnova_opportunities.csv"})

# ── KPI Tracking ──────────────────────────────────────────────────────────────

@app.get("/api/kpi/templates")
def kpi_template_list(category:str=Query(default=""),u=Depends(current_user)):
    stmt=select(kpi_templates).where(kpi_templates.c.active==True).order_by(kpi_templates.c.category,kpi_templates.c.sort_order)
    if category: stmt=stmt.where(kpi_templates.c.category.in_(category_names(category)))
    return [{**t,"category":canon_category(t["category"])} for t in rows(stmt)]

@app.get("/api/kpi/targets")
def kpi_target_list(category:str=Query(default=""),month:str=Query(default=""),u=Depends(current_user)):
    stmt=select(kpi_targets,kpi_templates.c.category,kpi_templates.c.kra,kpi_templates.c.kpi,kpi_templates.c.sort_order).select_from(kpi_targets.join(kpi_templates,kpi_templates.c.id==kpi_targets.c.template_id)).order_by(kpi_templates.c.category,kpi_templates.c.sort_order)
    if category: stmt=stmt.where(kpi_templates.c.category.in_(category_names(category)))
    if month: stmt=stmt.where(kpi_targets.c.month==month)
    return [{**t,"category":canon_category(t["category"])} for t in rows(stmt)]

@app.put("/api/kpi/targets")
def kpi_target_upsert(p:Payload,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only admins can set KPI targets")
    d=p.data; tid=int(d["template_id"]); month=d["month"]; val=float(d["target_value"])
    existing=row(select(kpi_targets).where(and_(kpi_targets.c.template_id==tid,kpi_targets.c.month==month)))
    if existing:
        execute(update(kpi_targets).where(kpi_targets.c.id==existing["id"]).values(target_value=val,updated_at=utcnow()))
    else:
        execute(insert(kpi_targets).values(template_id=tid,month=month,target_value=val,created_by=u["id"]))
    return {"ok":True}

@app.get("/api/kpi/my")
def kpi_my_actuals(month:str=Query(default=""),u=Depends(current_user)):
    """Return the current user's KPI sheet: templates + targets + actuals for their category."""
    cat=u.get("category")
    if not cat: return {"category":None,"items":[]}
    cat=canon_category(cat)
    tpls=[{**t,"category":cat} for t in rows(select(kpi_templates).where(and_(kpi_templates.c.category.in_(category_names(cat)),kpi_templates.c.active==True)).order_by(kpi_templates.c.sort_order))]
    if not month: month=date.today().strftime("%Y-%m")
    tgt_map={}
    for t in rows(select(kpi_targets).where(and_(kpi_targets.c.template_id.in_([x["id"] for x in tpls]),kpi_targets.c.month==month))):
        tgt_map[t["template_id"]]=t["target_value"]
    act_map={}
    for a in rows(select(kpi_actuals).where(and_(kpi_actuals.c.user_id==u["id"],kpi_actuals.c.template_id.in_([x["id"] for x in tpls]),kpi_actuals.c.month==month))):
        act_map[a["template_id"]]=a
    items=[]
    for t in tpls:
        act=act_map.get(t["id"],{})
        items.append({**t,"target_value":tgt_map.get(t["id"],0),"actual_value":act.get("actual_value"),"actual_remarks":act.get("remarks"),"actual_status":act.get("status","draft"),"review_remarks":act.get("review_remarks"),"actual_id":act.get("id")})
    return {"category":cat,"month":month,"items":items}

@app.put("/api/kpi/actuals")
def kpi_actual_upsert(p:Payload,u=Depends(require_csrf)):
    """User submits or updates their own KPI actual for a given template+month."""
    d=p.data; tid=int(d["template_id"]); month=d["month"]; val=float(d["actual_value"]); remarks=d.get("remarks","")
    status=d.get("status","draft")
    if status not in ("draft","submitted"): status="draft"
    existing=row(select(kpi_actuals).where(and_(kpi_actuals.c.user_id==u["id"],kpi_actuals.c.template_id==tid,kpi_actuals.c.month==month)))
    if existing:
        if existing["status"]=="approved": raise HTTPException(400,"Cannot edit an approved KPI entry")
        execute(update(kpi_actuals).where(kpi_actuals.c.id==existing["id"]).values(actual_value=val,remarks=remarks,status=status,updated_at=utcnow()))
    else:
        execute(insert(kpi_actuals).values(user_id=u["id"],template_id=tid,month=month,actual_value=val,remarks=remarks,status=status))
    return {"ok":True}

@app.post("/api/kpi/submit")
def kpi_submit_month(p:Payload,u=Depends(require_csrf)):
    """Mark all draft actuals for a month as submitted."""
    month=p.data.get("month") or date.today().strftime("%Y-%m")
    cat=u.get("category")
    if not cat: raise HTTPException(400,"No category assigned to your profile")
    tpl_ids=[t["id"] for t in rows(select(kpi_templates.c.id).where(kpi_templates.c.category.in_(category_names(cat))))]
    execute(update(kpi_actuals).where(and_(kpi_actuals.c.user_id==u["id"],kpi_actuals.c.template_id.in_(tpl_ids),kpi_actuals.c.month==month,kpi_actuals.c.status=="draft")).values(status="submitted",updated_at=utcnow()))
    return {"ok":True}

@app.get("/api/kpi/review")
def kpi_review_list(month:str=Query(default=""),user_id:int=Query(default=0),u=Depends(current_user)):
    """Admin/Super Admin: list all users' submitted/approved KPI actuals for review."""
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Review requires admin role")
    if not month: month=date.today().strftime("%Y-%m")
    uu=users.alias("uu")
    stmt=select(kpi_actuals,kpi_templates.c.category,kpi_templates.c.kra,kpi_templates.c.kpi,kpi_templates.c.sort_order,uu.c.name.label("user_name"),uu.c.category.label("user_category")).select_from(kpi_actuals.join(kpi_templates,kpi_templates.c.id==kpi_actuals.c.template_id).join(uu,uu.c.id==kpi_actuals.c.user_id)).where(and_(kpi_actuals.c.month==month,kpi_actuals.c.status.in_(["submitted","approved","rejected"]))).order_by(uu.c.name,kpi_templates.c.sort_order)
    if user_id: stmt=stmt.where(kpi_actuals.c.user_id==user_id)
    items=rows(stmt)
    for i in items: i["category"]=canon_category(i["category"]); i["user_category"]=canon_category(i["user_category"])
    # Also fetch targets for these templates
    tpl_ids=list({i["template_id"] for i in items})
    tgt_map={}
    if tpl_ids:
        for t in rows(select(kpi_targets).where(and_(kpi_targets.c.template_id.in_(tpl_ids),kpi_targets.c.month==month))):
            tgt_map[t["template_id"]]=t["target_value"]
    for i in items: i["target_value"]=tgt_map.get(i["template_id"],0)
    # Group by user
    by_user={}
    for i in items:
        uid=i["user_id"]
        if uid not in by_user: by_user[uid]={"user_id":uid,"user_name":i["user_name"],"category":i["user_category"],"items":[]}
        by_user[uid]["items"].append(i)
    return list(by_user.values())

@app.put("/api/kpi/review/{actual_id}")
def kpi_review_action(actual_id:int,p:Payload,u=Depends(require_csrf)):
    """Admin approves or rejects a submitted KPI actual."""
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Review requires admin role")
    d=p.data; status=d.get("status")
    if status not in ("approved","rejected"): raise HTTPException(400,"Status must be approved or rejected")
    a=row(select(kpi_actuals).where(kpi_actuals.c.id==actual_id))
    if not a: raise HTTPException(404,"KPI entry not found")
    execute(update(kpi_actuals).where(kpi_actuals.c.id==actual_id).values(status=status,reviewed_by=u["id"],review_remarks=d.get("review_remarks",""),reviewed_at=utcnow(),updated_at=utcnow()))
    return {"ok":True}

@app.get("/api/kpi/users-with-category")
def kpi_users_with_category(u=Depends(current_user)):
    """List users that have a category assigned (for admin review dropdown)."""
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403)
    if not _HAS_CATEGORY: return []
    return [{**r,"category":canon_category(r["category"])} for r in rows(select(users.c.id,users.c.name,users.c.category).where(and_(users.c.category!=None,users.c.category!="",users.c.active==True)).order_by(users.c.name))]

@app.post("/api/kpi/templates")
def kpi_template_create(p:Payload,u=Depends(require_csrf)):
    """Admin creates a new KPI template with optional target for a month."""
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only admins can create KPI templates")
    d=p.data
    if not d.get("category") or not d.get("kra") or not d.get("kpi"): raise HTTPException(400,"Category, KRA and KPI are required")
    cat=canon_category(d["category"])
    max_sort=row(select(func.max(kpi_templates.c.sort_order).label("mx")).where(kpi_templates.c.category.in_(category_names(cat))))
    sort_order=(max_sort["mx"] or 0)+1 if max_sort else 1
    tid=execute(insert(kpi_templates).values(category=cat,kra=d["kra"],kpi=d["kpi"],sort_order=sort_order,active=True))
    if d.get("month") and d.get("target_value") is not None:
        execute(insert(kpi_targets).values(template_id=tid,month=d["month"],target_value=float(d["target_value"]),created_by=u["id"]))
    return {"ok":True,"id":tid}

@app.put("/api/kpi/templates/{template_id}")
def kpi_template_update(template_id:int,p:Payload,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403)
    d=p.data; vals={}
    if d.get("kra"): vals["kra"]=d["kra"]
    if d.get("kpi"): vals["kpi"]=d["kpi"]
    if d.get("category"): vals["category"]=canon_category(d["category"])
    if not vals: raise HTTPException(400,"Nothing to update")
    execute(update(kpi_templates).where(kpi_templates.c.id==template_id).values(**vals))
    return {"ok":True}

@app.delete("/api/kpi/templates/{template_id}")
def kpi_template_delete(template_id:int,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403)
    execute(delete(kpi_actuals).where(kpi_actuals.c.template_id==template_id))
    execute(delete(kpi_targets).where(kpi_targets.c.template_id==template_id))
    execute(delete(kpi_templates).where(kpi_templates.c.id==template_id))
    return {"ok":True}

@app.get("/api/kpi/admin-sheet")
def kpi_admin_sheet(category:str=Query(default=""),month:str=Query(default=""),u=Depends(current_user)):
    """Admin view: all templates for a category with targets + all users' actuals for that month."""
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403)
    if not month: month=date.today().strftime("%Y-%m")
    stmt=select(kpi_templates).where(kpi_templates.c.active==True).order_by(kpi_templates.c.sort_order)
    if category: stmt=stmt.where(kpi_templates.c.category.in_(category_names(category)))
    tpls=[{**t,"category":canon_category(t["category"])} for t in rows(stmt)]
    tpl_ids=[t["id"] for t in tpls]
    tgt_map={}
    if tpl_ids:
        for t in rows(select(kpi_targets).where(and_(kpi_targets.c.template_id.in_(tpl_ids),kpi_targets.c.month==month))):
            tgt_map[t["template_id"]]=t["target_value"]
    # Get all users' actuals for these templates
    act_by_user={}
    if tpl_ids:
        uu=users.alias("uu")
        for a in rows(select(kpi_actuals,uu.c.name.label("user_name")).select_from(kpi_actuals.join(uu,uu.c.id==kpi_actuals.c.user_id)).where(and_(kpi_actuals.c.template_id.in_(tpl_ids),kpi_actuals.c.month==month))):
            key=a["template_id"]
            if key not in act_by_user: act_by_user[key]=[]
            act_by_user[key].append({"user_id":a["user_id"],"user_name":a["user_name"],"actual_value":a["actual_value"],"status":a["status"]})
    items=[]
    for t in tpls:
        items.append({**t,"target_value":tgt_map.get(t["id"],0),"actuals":act_by_user.get(t["id"],[])})
    return {"month":month,"items":items}

# ── CSV Import ────────────────────────────────────────────────────────────────

SAMPLE_CSV_HEADER = "Company,Vertical,Region,Country,Contact Name,Designation,Email,Phone,Signal,Source,Status,Next Follow-up,Remarks,Owner Email"
SAMPLE_CSV_ROWS = [
    "Acme Corp,Telecommunications,North America,USA,John Smith,VP Engineering,john@acme.com,+1-555-0100,Warm,LinkedIn,New,2026-10-15,Interested in geospatial services,bd.exec1@jsan.local",
    "GlobalTech Ltd,Data & AI,Europe,UK,Jane Doe,Director,jane@globaltech.com,+44-20-1234,Hot,Referral,Engaged,2026-10-10,Active discussion on AI pipeline,bd.exec2@jsan.local",
]
STATUS_MAP = {
    "outreach sent": "Contacted", "follow-up sent": "Contacted", "qualified response": "Qualified",
    "active discussion": "Engaged", "meeting scheduled": "Engaged", "nurture": "On Hold",
    "new": "New", "assigned": "Assigned", "contacted": "Contacted", "engaged": "Engaged",
    "qualified": "Qualified", "converted": "Converted", "on hold": "On Hold",
    "unresponsive": "Unresponsive", "disqualified": "Disqualified", "lost": "Lost",
}
VALID_STATUSES = {"New","Assigned","Contacted","Engaged","Qualified","Converted","On Hold","Unresponsive","Disqualified","Lost"}
VALID_SIGNALS = {"Hot","Warm","Cold"}

@app.get("/api/leads/import/sample")
def download_sample_csv(u=Depends(require_perm("LEAD_CREATE"))):
    content = SAMPLE_CSV_HEADER + "\n" + "\n".join(SAMPLE_CSV_ROWS) + "\n"
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=pursuitnova_import_sample.csv"})

@app.post("/api/leads/import")
def import_leads_csv(file: UploadFile = File(...), u=Depends(require_csrf)):
    if "LEAD_CREATE" not in u.get("permissions", []): raise HTTPException(403, "Lead create permission required")
    # Read and parse CSV
    try:
        raw = file.file.read()
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try: text = raw.decode(enc); break
            except Exception: continue
        else: raise ValueError("Unable to decode file")
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        raise HTTPException(400, f"Cannot read CSV: {e}")

    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    required = {"company"}
    missing_cols = required - {f.replace(" ", "").replace("_", "") for f in fields}
    if missing_cols:
        raise HTTPException(400, f"Missing required column(s): {', '.join(required)}. Found: {', '.join(reader.fieldnames or [])}")

    # Resolve owner lookup cache
    user_cache = {}; user_names = {}
    for ur in rows(select(users.c.id, users.c.name, users.c.email)):
        user_cache[ur["email"].lower()] = ur["id"]
        user_cache[ur["name"].lower()] = ur["id"]
        user_names[ur["id"]] = ur["name"]
    assignable_cache = {}  # owner id -> may this importer assign to them (same rule as creating a prospect)

    results = {"imported": 0, "skipped": 0, "errors": [], "warnings": []}

    for idx, raw_row in enumerate(reader, start=2):
        row_num = idx
        r = {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in raw_row.items() if k}
        company_name = r.get("company", "").strip()
        if not company_name:
            results["errors"].append({"row": row_num, "message": "Company name is empty — row skipped"})
            results["skipped"] += 1
            continue

        # Resolve owner
        owner_key = (r.get("owner_email") or r.get("owner") or "").strip().lower()
        owner_id = user_cache.get(owner_key, u["id"])
        if owner_key and owner_key not in user_cache:
            results["warnings"].append({"row": row_num, "message": f"Owner '{r.get('owner_email') or r.get('owner')}' not found — assigned to you"})
        elif owner_id != u["id"]:
            if owner_id not in assignable_cache: assignable_cache[owner_id] = can_assign(u, owner_id)
            if not assignable_cache[owner_id]:
                results["warnings"].append({"row": row_num, "message": f"You cannot assign prospects to {user_names.get(owner_id, 'that user')} — assigned to you"})
                owner_id = u["id"]

        # Map status
        raw_status = (r.get("status") or "New").strip()
        status = STATUS_MAP.get(raw_status.lower(), raw_status)
        if status not in VALID_STATUSES:
            results["warnings"].append({"row": row_num, "message": f"Unknown status '{raw_status}' — defaulted to 'New'"})
            status = "New"

        # Map signal
        signal = (r.get("signal") or r.get("temperature") or "Warm").strip().title()
        if signal not in VALID_SIGNALS:
            results["warnings"].append({"row": row_num, "message": f"Unknown signal '{signal}' — defaulted to 'Warm'"})
            signal = "Warm"

        # Check duplicate company
        norm = normalize_name(company_name)
        existing_company = row(select(companies.c.id, companies.c.name).where(companies.c.normalized_name == norm)) if norm else None

        try:
            if existing_company:
                company_id = existing_company["id"]
                results["warnings"].append({"row": row_num, "message": f"Company '{company_name}' already exists — linked to existing"})
            else:
                company_id = execute(insert(companies).values(
                    name=company_name, normalized_name=norm,
                    vertical=classify_vertical(r.get("vertical")) or "Other",
                    website=r.get("website") or None, domain=domain_from_url(r.get("website")),
                    region=r.get("region") or None, country=r.get("country") or None,
                    state=r.get("state") or None, city=r.get("city") or None,
                    status="Active", created_by=u["id"]
                ))

            # Check duplicate lead for same company
            existing_lead = row(select(leads.c.id).where(leads.c.company_id == company_id))
            if existing_lead:
                results["warnings"].append({"row": row_num, "message": f"Lead for '{company_name}' already exists — skipped lead creation"})
                results["skipped"] += 1
                continue

            # Parse follow-up date
            next_fu = None
            raw_fu = r.get("next_follow-up") or r.get("next_follow_up") or r.get("next_action_date") or ""
            if raw_fu:
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
                    try: next_fu = datetime.strptime(raw_fu, fmt).strftime("%Y-%m-%d"); break
                    except Exception: pass

            source = r.get("source") or "Other"
            remarks = r.get("remarks") or r.get("received_summary") or r.get("next_action") or ""

            lead_id = execute(insert(leads).values(
                company_id=company_id, owner_id=owner_id,
                temperature=signal, source=source, status=status,
                region=r.get("region") or None, country=r.get("country") or None,
                next_follow_up=next_fu, remarks=remarks, created_by=u["id"]
            ))

            # Create contact if provided
            contact_name = r.get("contact_name") or r.get("contact") or ""
            if contact_name:
                emails = [e.strip() for e in (r.get("email") or "").split(";") if e.strip() and "@" in e]
                primary_email = emails[0] if emails else None
                ne = normalize_email(primary_email)
                execute(insert(contacts).values(
                    company_id=company_id, name=contact_name,
                    designation=r.get("designation") or None,
                    email=primary_email, normalized_email=ne,
                    phone=r.get("phone") or None,
                    is_primary=True, active=True, created_by=u["id"]
                ))
                # Additional contacts from semicolon-separated emails
                for extra_email in emails[1:]:
                    ene = normalize_email(extra_email)
                    if ene and not row(select(contacts.c.id).where(and_(contacts.c.company_id == company_id, contacts.c.normalized_email == ene))):
                        execute(insert(contacts).values(
                            company_id=company_id, name=extra_email.split("@")[0],
                            email=extra_email, normalized_email=ene,
                            is_primary=False, active=True, created_by=u["id"]
                        ))

            # Create action from "Next action" or "Sent subject"
            action_desc = r.get("next_action") or r.get("sent_subject") or None
            if action_desc and lead_id:
                execute(insert(actions).values(
                    lead_id=lead_id, action_date=today_str(),
                    description=action_desc, assigned_to=owner_id,
                    due_date=next_fu or (date.today() + timedelta(days=7)).isoformat(),
                    status="Open", priority="Medium", created_by=u["id"]
                ))

            audit(u["id"], "lead", lead_id, "IMPORT", {"company": company_name, "source": "csv"})
            results["imported"] += 1

        except IntegrityError as e:
            results["errors"].append({"row": row_num, "message": f"Database error: {str(e)[:100]}"})
            results["skipped"] += 1
        except Exception as e:
            results["errors"].append({"row": row_num, "message": str(e)[:150]})
            results["skipped"] += 1

    return results


# ══════════════════════════════════════════════════════════════════════════════
# Partnerships: a second, fully independent pipeline with the same features and
# rules as Prospects (own tables — see app/db.py — so nothing here can ever
# change a prospect, a company, a report or a dashboard number).
# ══════════════════════════════════════════════════════════════════════════════

def can_view_partnership(u, partnership_id: int) -> bool:
    l=row(select(partnerships.c.owner_id).where(partnerships.c.id==partnership_id))
    if not l: return False
    if l["owner_id"] in scope_user_ids(u) or has_share("partnership", partnership_id, u["id"]): return True
    if u["role"] == "Presales Lead":
        if row(select(partner_actions.c.id).where(and_(partner_actions.c.partnership_id==partnership_id, partner_actions.c.assigned_to==u["id"])).limit(1)): return True
        if row(select(partner_opportunity_team.c.opportunity_id).select_from(partner_opportunity_team.join(partner_opportunities, partner_opportunities.c.id==partner_opportunity_team.c.opportunity_id)).where(and_(partner_opportunities.c.partnership_id==partnership_id, partner_opportunity_team.c.user_id==u["id"])).limit(1)): return True
    return False

def can_edit_partnership(u, partnership_id: int) -> bool:
    if "LEAD_EDIT" not in u["permissions"]: return False
    l=row(select(partnerships.c.owner_id).where(partnerships.c.id==partnership_id))
    return bool(l and (l["owner_id"] in scope_user_ids(u) or has_share("partnership", partnership_id, u["id"], True)))

def can_view_partner_opp(u, opp_id: int) -> bool:
    o=row(select(partner_opportunities.c.owner_id, partner_opportunities.c.presales_owner_id).where(partner_opportunities.c.id==opp_id))
    if not o: return False
    if o["owner_id"] in scope_user_ids(u) or o.get("presales_owner_id")==u["id"] or has_share("partner_opportunity", opp_id, u["id"]): return True
    return bool(row(select(partner_opportunity_team.c.opportunity_id).where(and_(partner_opportunity_team.c.opportunity_id==opp_id, partner_opportunity_team.c.user_id==u["id"]))))

def can_edit_partner_opp(u, opp_id: int) -> bool:
    return "OPPORTUNITY_EDIT" in u["permissions"] and can_view_partner_opp(u, opp_id)

def can_access_partner_company_relationship(u, company_id: int) -> bool:
    if u.get("scope_type") == "all": return True
    for lr in rows(select(partnerships.c.id).where(partnerships.c.company_id==company_id)):
        if can_view_partnership(u, lr["id"]): return True
    for op in rows(select(partner_opportunities.c.id).where(partner_opportunities.c.company_id==company_id)):
        if can_view_partner_opp(u, op["id"]): return True
    return False

def partner_opportunity_rows(u):
    puo=users.alias("puo"); pup=users.alias("pup")
    stmt=select(partner_opportunities, partner_companies.c.name.label("company_name"), partner_companies.c.vertical, puo.c.name.label("owner_name"), pup.c.name.label("presales_owner_name"), partnerships.c.temperature).select_from(
        partner_opportunities.join(partner_companies, partner_companies.c.id==partner_opportunities.c.company_id).join(partnerships, partnerships.c.id==partner_opportunities.c.partnership_id).join(puo, puo.c.id==partner_opportunities.c.owner_id).outerjoin(pup, pup.c.id==partner_opportunities.c.presales_owner_id)
    )
    base=rows(stmt.order_by(partner_opportunities.c.updated_at.desc()))
    out=[]
    for x in base:
        if can_view_partner_opp(u,x["id"]):
            try: x["age_days"]=(date.today()-x["created_at"].date()).days
            except Exception: x["age_days"]=0
            out.append(mask_fields(u,"opportunity",x))
    return out

def partnership_rows(u):
    powner=users.alias("powner")
    stmt=select(partnerships, partner_companies.c.name.label("company_name"), partner_companies.c.vertical, partner_companies.c.website, partner_companies.c.linkedin_url, partner_companies.c.external_url, powner.c.name.label("owner_name")).select_from(
        partnerships.join(partner_companies, partner_companies.c.id==partnerships.c.company_id).join(powner, powner.c.id==partnerships.c.owner_id)
    ).order_by(partnerships.c.updated_at.desc())
    base=rows(stmt); out=[]
    for x in base:
        if can_view_partnership(u,x["id"]):
            ct=row(select(partner_contacts.c.name).where(partner_contacts.c.company_id==x["company_id"]).order_by(partner_contacts.c.is_primary.desc(),partner_contacts.c.id).limit(1))
            x["primary_contact"]=ct["name"] if ct else None
            ac=row(select(func.count()).select_from(partner_actions).where(and_(partner_actions.c.partnership_id==x["id"], partner_actions.c.status.not_in(["Completed","Cancelled"]))))
            x["open_actions"]=list(ac.values())[0] if ac else 0
            x["last_activity"]=(x["updated_at"].date().isoformat() if x.get("updated_at") else None)
            out.append(x)
    temporder={"Hot":0,"Warm":1,"Cold":2}; out.sort(key=lambda x:(temporder.get(x["temperature"],9), str(x.get("updated_at"))), reverse=False)
    return out

def duplicate_partner_companies(name,website):
    nn=normalize_name(name); domain=domain_from_url(website); candidates=[]
    for c in rows(select(partner_companies).where(partner_companies.c.status!="Merged")):
        score=0; reasons=[]
        if nn and c["normalized_name"]==nn: score+=0.75; reasons.append("same normalized name")
        elif nn and (nn in c["normalized_name"] or c["normalized_name"] in nn): score+=0.45; reasons.append("similar name")
        if domain and c.get("domain")==domain: score+=0.55; reasons.append("same website domain")
        if score>=0.45: candidates.append({"company":c,"score":round(min(score,1),2),"reasons":reasons})
    return sorted(candidates,key=lambda x:x["score"],reverse=True)

def partnership_visibility_condition(u):
    owner_ids=scope_user_ids(u)
    conds=[partnerships.c.owner_id.in_(owner_ids)]
    shared=select(record_shares.c.entity_id).where(and_(record_shares.c.entity_type=="partnership",record_shares.c.user_id==u["id"]))
    conds.append(partnerships.c.id.in_(shared))
    return or_(*conds)

@app.post("/api/partner-companies")
def create_partner_company(p:Payload,u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403,"Company edit permission required")
    d=p.data
    if not d.get("name") or not d.get("vertical"): raise HTTPException(400,"Company name and vertical are required")
    dups=duplicate_partner_companies(d["name"],d.get("website"))
    if dups and dups[0]["score"]>=0.75: raise HTTPException(409,f"Potential duplicate company: {dups[0]['company']['name']}. Reuse the existing company or review duplicates.")
    cid=execute(insert(partner_companies).values(name=d["name"].strip(),normalized_name=normalize_name(d["name"]),vertical=classify_vertical(d["vertical"]),website=d.get("website"),domain=domain_from_url(d.get("website")),linkedin_url=d.get("linkedin_url"),external_url=d.get("external_url"),region=d.get("region"),country=d.get("country"),state=d.get("state"),city=d.get("city"),remarks=d.get("remarks"),status="Active",created_by=u["id"]))
    audit(u["id"],"partner_company",cid,"CREATE",d); return row(select(partner_companies).where(partner_companies.c.id==cid))

@app.get("/api/partner-companies/{company_id}")
def partner_company_detail(company_id:int,u=Depends(require_perm("COMPANY_VIEW"))):
    c=row(select(partner_companies).where(partner_companies.c.id==company_id))
    if not c: raise HTTPException(404,"Company not found")
    rel=can_access_partner_company_relationship(u,company_id)
    return {"company":c,"contacts":[mask_fields(u,"contact",x) for x in rows(select(partner_contacts).where(partner_contacts.c.company_id==company_id).order_by(partner_contacts.c.is_primary.desc(),partner_contacts.c.id))] if rel else [],"relationship_access":rel,"partnerships":[x for x in partnership_rows(u) if x["company_id"]==company_id],"opportunities":[x for x in partner_opportunity_rows(u) if x["company_id"]==company_id]}

@app.put("/api/partner-companies/{company_id}")
def update_partner_company(company_id:int,p:Payload,u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403,"Company edit permission required")
    if not row(select(partner_companies.c.id).where(partner_companies.c.id==company_id)): raise HTTPException(404,"Company not found")
    if not can_access_partner_company_relationship(u,company_id): raise HTTPException(403,"Company relationship edit denied")
    d=p.data; vals={k:d[k] for k in ("name","vertical","website","linkedin_url","external_url","region","country","state","city","remarks","status") if k in d}
    for k in ("name","vertical"):
        if k in vals:
            vals[k]=_clean_text(vals[k],220 if k=="name" else None)
            if not vals[k]: raise HTTPException(400,f"Company {k} is required")
    if "vertical" in vals: vals["vertical"]=classify_vertical(vals["vertical"])
    for k,label,n in (("region","Region",80),("country","Country",100),("state","State",100),("city","City",100),("remarks","Company notes",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    for k,label in (("website","Website"),("linkedin_url","Company LinkedIn page"),("external_url","Other link")):
        if k in vals: vals[k]=_clean_url(vals[k],label)
    if "name" in vals:
        vals["normalized_name"]=normalize_name(vals["name"])
        clash=row(select(partner_companies.c.id,partner_companies.c.name).where(and_(partner_companies.c.normalized_name==vals["normalized_name"],partner_companies.c.id!=company_id,partner_companies.c.status!="Merged")))
        if clash: raise HTTPException(409,f"Another company is already named {clash['name']}")
    if "website" in vals: vals["domain"]=domain_from_url(vals["website"])
    vals["updated_at"]=utcnow(); execute(update(partner_companies).where(partner_companies.c.id==company_id).values(**vals)); audit(u["id"],"partner_company",company_id,"UPDATE",d); return row(select(partner_companies).where(partner_companies.c.id==company_id))

@app.post("/api/partner-companies/{company_id}/contacts")
def add_partner_contact(company_id:int,p:Payload,u=Depends(require_csrf)):
    if "CONTACT_EDIT" not in u["permissions"]: raise HTTPException(403,"Contact edit permission required")
    if not can_access_partner_company_relationship(u,company_id): raise HTTPException(403,"Company relationship access denied")
    d=p.data; ensure_fields_editable(u,"contact",d)
    if not d.get("name"): raise HTTPException(400,"Contact name is required")
    ne=normalize_email(d.get("email"))
    if ne and row(select(partner_contacts.c.id).where(and_(partner_contacts.c.company_id==company_id,partner_contacts.c.normalized_email==ne,partner_contacts.c.active==True))): raise HTTPException(409,"A contact with this email already exists for the company")
    cid=execute(insert(partner_contacts).values(company_id=company_id,name=d["name"],designation=d.get("designation"),department=d.get("department"),email=d.get("email"),normalized_email=ne,phone=d.get("phone"),linkedin_url=d.get("linkedin_url"),location=d.get("location"),remarks=d.get("remarks"),is_primary=bool(d.get("is_primary")),active=True,created_by=u["id"]))
    audit(u["id"],"partner_contact",cid,"CREATE",d); return mask_fields(u,"contact",row(select(partner_contacts).where(partner_contacts.c.id==cid)))

@app.put("/api/partner-contacts/{contact_id}")
def update_partner_contact(contact_id:int,p:Payload,u=Depends(require_csrf)):
    if "CONTACT_EDIT" not in u["permissions"]: raise HTTPException(403,"Contact edit permission required")
    cr=row(select(partner_contacts.c.company_id).where(partner_contacts.c.id==contact_id))
    if not cr: raise HTTPException(404,"Contact not found")
    if not can_access_partner_company_relationship(u,int(cr["company_id"])): raise HTTPException(403,"Contact relationship access denied")
    d=p.data; ensure_fields_editable(u,"contact",d); vals={k:d[k] for k in ("name","designation","department","email","phone","linkedin_url","location","remarks","is_primary","active") if k in d}
    if "name" in vals:
        vals["name"]=_clean_text(vals["name"],180)
        if not vals["name"]: raise HTTPException(400,"Contact name is required")
    for k,n in (("designation",180),("department",120),("phone",80),("location",220),("remarks",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    if "linkedin_url" in vals: vals["linkedin_url"]=_clean_url(vals["linkedin_url"],"LinkedIn profile")
    if "email" in vals:
        vals["email"]=_clean_text(vals["email"],190)
        if vals["email"] and ("@" not in vals["email"] or " " in vals["email"]): raise HTTPException(400,"Email address is not valid")
        vals["normalized_email"]=normalize_email(vals["email"])
        if vals["normalized_email"] and row(select(partner_contacts.c.id).where(and_(partner_contacts.c.company_id==cr["company_id"],partner_contacts.c.normalized_email==vals["normalized_email"],partner_contacts.c.active==True,partner_contacts.c.id!=contact_id))):
            raise HTTPException(409,"Another contact at this company already uses this email")
    if "is_primary" in vals: vals["is_primary"]=bool(vals["is_primary"])
    if "active" in vals: vals["active"]=bool(vals["active"])
    if vals.get("is_primary"): execute(update(partner_contacts).where(and_(partner_contacts.c.company_id==cr["company_id"],partner_contacts.c.id!=contact_id)).values(is_primary=False,updated_at=utcnow()))
    vals["updated_at"]=utcnow(); execute(update(partner_contacts).where(partner_contacts.c.id==contact_id).values(**vals)); audit(u["id"],"partner_contact",contact_id,"UPDATE",d); return mask_fields(u,"contact",row(select(partner_contacts).where(partner_contacts.c.id==contact_id)))

@app.post("/api/partnerships/full")
def create_partnership_full(p:Payload,u=Depends(require_csrf)):
    if "LEAD_CREATE" not in u["permissions"]: raise HTTPException(403,"Lead create permission required")
    d=p.data; l=d.get("lead") or {}; owner_id=int(l.get("owner_id") or u["id"])
    if not can_assign(u,owner_id): raise HTTPException(403,"You cannot assign this partnership to that user")
    company_id=d.get("company_id")
    if company_id:
        if not row(select(partner_companies.c.id).where(partner_companies.c.id==int(company_id))): raise HTTPException(404,"Company not found")
        company_id=int(company_id)
    else:
        comp=d.get("company") or {}
        if not comp.get("name") or not comp.get("vertical"): raise HTTPException(400,"Company name and vertical are required")
        dups=duplicate_partner_companies(comp["name"],comp.get("website"))
        if dups and dups[0]["score"]>=0.75: raise HTTPException(409,f"Potential duplicate company: {dups[0]['company']['name']}. Select the existing company.")
        company_id=execute(insert(partner_companies).values(name=comp["name"].strip(),normalized_name=normalize_name(comp["name"]),vertical=classify_vertical(comp["vertical"]),website=comp.get("website"),domain=domain_from_url(comp.get("website")),linkedin_url=comp.get("linkedin_url"),external_url=comp.get("external_url"),region=comp.get("region") or l.get("region"),country=comp.get("country") or l.get("country"),state=comp.get("state") or l.get("state"),city=comp.get("city") or l.get("city"),remarks=comp.get("remarks"),status="Active",created_by=u["id"]))
    partnership_id=execute(insert(partnerships).values(company_id=company_id,owner_id=owner_id,temperature=l.get("temperature") or "Warm",source=l.get("source") or "LinkedIn",source_detail=l.get("source_detail"),status=l.get("status") or "New",region=l.get("region"),country=l.get("country"),state=l.get("state"),city=l.get("city"),next_follow_up=l.get("next_follow_up"),remarks=l.get("remarks"),created_by=u["id"]))
    for idx,ct in enumerate(d.get("contacts") or []):
        if ct.get("name"):
            ne=normalize_email(ct.get("email"))
            if ne and row(select(partner_contacts.c.id).where(and_(partner_contacts.c.company_id==company_id,partner_contacts.c.normalized_email==ne,partner_contacts.c.active==True))): continue
            execute(insert(partner_contacts).values(company_id=company_id,name=ct["name"],designation=ct.get("designation"),department=ct.get("department"),email=ct.get("email"),normalized_email=ne,phone=ct.get("phone"),linkedin_url=ct.get("linkedin_url"),location=ct.get("location"),remarks=ct.get("remarks"),is_primary=bool(ct.get("is_primary") or idx==0),active=True,created_by=u["id"]))
    audit(u["id"],"partnership",partnership_id,"CREATE",{"company_id":company_id,"owner_id":owner_id}); return partnership_detail(partnership_id,u)

@app.get("/api/partnerships")
def list_partnerships(u=Depends(require_perm("LEAD_VIEW"))): return partnership_rows(u)

@app.get("/api/partnerships/{partnership_id}")
def partnership_detail(partnership_id:int,u=Depends(require_perm("LEAD_VIEW"))):
    if not can_view_partnership(u,partnership_id): raise HTTPException(403,"You do not have access to this partnership")
    powner=users.alias("powner2")
    l=row(select(partnerships,partner_companies.c.name.label("company_name"),partner_companies.c.vertical,partner_companies.c.website,partner_companies.c.linkedin_url,partner_companies.c.external_url,partner_companies.c.remarks.label("company_remarks"),powner.c.name.label("owner_name")).select_from(partnerships.join(partner_companies,partner_companies.c.id==partnerships.c.company_id).join(powner,powner.c.id==partnerships.c.owner_id)).where(partnerships.c.id==partnership_id))
    cts=[mask_fields(u,"contact",x) for x in rows(select(partner_contacts).where(and_(partner_contacts.c.company_id==l["company_id"],partner_contacts.c.active==True)).order_by(partner_contacts.c.is_primary.desc(),partner_contacts.c.id))]
    mts=rows(select(partner_meetings).where(partner_meetings.c.partnership_id==partnership_id).order_by(partner_meetings.c.meeting_date.desc(),partner_meetings.c.id.desc()))
    ms=rows(select(partner_moms).where(partner_moms.c.partnership_id==partnership_id).order_by(partner_moms.c.id.desc()))
    att_by_mom={}
    for a in rows(select(partner_mom_attachments.c.id,partner_mom_attachments.c.mom_id,partner_mom_attachments.c.filename,partner_mom_attachments.c.size_bytes,partner_mom_attachments.c.uploaded_by,partner_mom_attachments.c.created_at,users.c.name.label("uploaded_by_name")).select_from(partner_mom_attachments.join(users,users.c.id==partner_mom_attachments.c.uploaded_by)).where(partner_mom_attachments.c.partnership_id==partnership_id).order_by(partner_mom_attachments.c.id)):
        a["can_delete"]=a["uploaded_by"]==u["id"] or u["role"] in ("Super Admin","Admin")
        att_by_mom.setdefault(a["mom_id"],[]).append(a)
    for mo in ms: mo["attachments"]=att_by_mom.get(mo["id"],[])
    paa=users.alias("paa")
    acts=rows(select(partner_actions,paa.c.name.label("assigned_to_name")).select_from(partner_actions.join(paa,paa.c.id==partner_actions.c.assigned_to)).where(partner_actions.c.partnership_id==partnership_id).order_by(partner_actions.c.due_date,partner_actions.c.id.desc()))
    for a in acts: a["overdue"]=a["status"] not in ("Completed","Cancelled") and a["due_date"]<today_str()
    opps=[x for x in partner_opportunity_rows(u) if x["partnership_id"]==partnership_id]
    fs=[]
    for o in opps:
        ff=rows(select(partner_followups).where(partner_followups.c.opportunity_id==o["id"]).order_by(partner_followups.c.follow_up_date.desc(),partner_followups.c.id.desc()))
        for f in ff: f["opportunity_name"]=o["name"]; f["owner_name"]=user_name(f["owner_id"])
        fs.extend(ff)
    docs=rows(select(documents).where(or_(and_(documents.c.entity_type=="partnership",documents.c.entity_id==partnership_id),and_(documents.c.entity_type=="partner_company",documents.c.entity_id==l["company_id"]))).order_by(documents.c.id.desc()))
    timeline=[]
    for m in mts: timeline.append({"date":m["meeting_date"],"type":"Meeting","title":m["meeting_type"],"detail":m.get("remarks") or m.get("purpose")})
    for mo in ms: timeline.append({"date":str(mo["created_at"])[:10],"type":"MoM","title":"Minutes of Meeting","detail":mo.get("summary")})
    for a in acts: timeline.append({"date":a["action_date"],"type":"Action","title":a["description"],"detail":f"{a['assigned_to_name']} · {a['status']} · due {a['due_date']}"})
    for o in opps: timeline.append({"date":str(o["created_at"])[:10],"type":"Opportunity","title":o["name"],"detail":f"{o['status']} · {o['forecast_category']}"})
    for f in fs: timeline.append({"date":f["follow_up_date"],"type":"Follow-up","title":f["opportunity_name"],"detail":f.get("response") or f.get("remarks")})
    timeline.sort(key=lambda x:x["date"] or "",reverse=True)
    last_edit=row(select(func.max(audit_logs.c.created_at).label("at")).where(and_(audit_logs.c.action=="UPDATE",or_(
        and_(audit_logs.c.entity_type=="partnership",audit_logs.c.entity_id==partnership_id),
        and_(audit_logs.c.entity_type=="partner_company",audit_logs.c.entity_id==l["company_id"])))))
    l["last_edited_at"]=iso_utc((last_edit or {}).get("at"))
    l["created_at_utc"]=iso_utc(l.get("created_at"))
    editable=can_edit_partnership(u,partnership_id)
    related=can_access_partner_company_relationship(u,l["company_id"])
    perms={"can_edit":editable,"can_edit_company":related and "COMPANY_EDIT" in u["permissions"],"can_edit_contacts":related and "CONTACT_EDIT" in u["permissions"],
           "can_reassign":editable and "LEAD_REASSIGN" in u["permissions"],"can_delete":editable and u["role"] in ("Super Admin","Admin")}
    perms["locked_contact_fields"]=[f for f in ("name","designation","email","phone","linkedin_url") if not all(field_access(u,"contact",f))]
    return {"lead":l,"contacts":cts,"meetings":mts,"moms":ms,"actions":acts,"opportunities":opps,"followups":fs,"documents":docs,"timeline":timeline,"permissions":perms}

@app.put("/api/partnerships/{partnership_id}")
def update_partnership(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_partnership(u,partnership_id): raise HTTPException(403,"You cannot edit this partnership")
    d=p.data; vals={k:d[k] for k in ("temperature","source","source_detail","status","region","country","state","city","next_follow_up","remarks") if k in d}
    if "temperature" in vals and vals["temperature"] not in LEAD_TEMPERATURES: raise HTTPException(400,"Signal must be Hot, Warm or Cold")
    if "status" in vals and vals["status"] not in LEAD_STATUSES: raise HTTPException(400,"Invalid partnership status")
    if "source" in vals:
        vals["source"]=_clean_text(vals["source"],80)
        if not vals["source"]: raise HTTPException(400,"Source is required")
    for k,n in (("source_detail",255),("region",80),("country",100),("state",100),("city",100),("remarks",None)):
        if k in vals: vals[k]=_clean_text(vals[k],n)
    if "next_follow_up" in vals:
        nf=_clean_text(vals["next_follow_up"])
        if nf:
            try: nf=datetime.strptime(nf,"%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError: raise HTTPException(400,"Next follow-up must be a valid date")
        vals["next_follow_up"]=nf
    if "owner_id" in d:
        oid=int(d["owner_id"])
        if "LEAD_REASSIGN" not in u["permissions"] or not can_assign(u,oid): raise HTTPException(403,"You cannot reassign this partnership")
        vals["owner_id"]=oid
    vals["updated_at"]=utcnow(); execute(update(partnerships).where(partnerships.c.id==partnership_id).values(**vals)); audit(u["id"],"partnership",partnership_id,"UPDATE",d); return partnership_detail(partnership_id,u)

@app.delete("/api/partnerships/{partnership_id}")
def delete_partnership(partnership_id:int,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only Super Admin and Admin can delete partnerships")
    l=row(select(partnerships,partner_companies.c.name.label("company_name")).select_from(partnerships.join(partner_companies,partner_companies.c.id==partnerships.c.company_id)).where(partnerships.c.id==partnership_id))
    if not l: raise HTTPException(404,"Partnership not found")
    if not can_edit_partnership(u,partnership_id): raise HTTPException(403,"You cannot delete this partnership")
    opp_ids=[r["id"] for r in rows(select(partner_opportunities.c.id).where(partner_opportunities.c.partnership_id==partnership_id))]
    if opp_ids:
        execute(delete(partner_followups).where(partner_followups.c.opportunity_id.in_(opp_ids)))
        execute(delete(partner_opportunity_team).where(partner_opportunity_team.c.opportunity_id.in_(opp_ids)))
        execute(delete(partner_opportunities).where(partner_opportunities.c.partnership_id==partnership_id))
    execute(delete(partner_actions).where(partner_actions.c.partnership_id==partnership_id))
    execute(delete(partner_mom_attachments).where(partner_mom_attachments.c.partnership_id==partnership_id))
    execute(delete(partner_moms).where(partner_moms.c.partnership_id==partnership_id))
    execute(delete(partner_meetings).where(partner_meetings.c.partnership_id==partnership_id))
    execute(delete(record_shares).where(and_(record_shares.c.entity_type=="partnership",record_shares.c.entity_id==partnership_id)))
    execute(delete(partnerships).where(partnerships.c.id==partnership_id))
    audit(u["id"],"partnership",partnership_id,"DELETE",{"company_name":l.get("company_name","")}); return {"ok":True}

@app.post("/api/partnerships/{partnership_id}/share")
def share_partnership(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if "SHARE_RECORD" not in u["permissions"] or not can_view_partnership(u,partnership_id): raise HTTPException(403,"Record-share permission required")
    target=int(p.data.get("user_id")); level=p.data.get("access_level") or "view"
    if not is_super(u) and org_root(target)!=org_root(u["id"]): raise HTTPException(403,"Records can only be shared within your own organisation")
    with engine.begin() as c:
        existing=c.execute(select(record_shares.c.id).where(and_(record_shares.c.entity_type=="partnership",record_shares.c.entity_id==partnership_id,record_shares.c.user_id==target))).fetchone()
        if existing: c.execute(update(record_shares).where(record_shares.c.id==existing.id).values(access_level=level))
        else: c.execute(insert(record_shares).values(entity_type="partnership",entity_id=partnership_id,user_id=target,access_level=level,created_by=u["id"]))
    audit(u["id"],"partnership",partnership_id,"SHARE",{"user_id":target,"access_level":level}); return {"ok":True}

@app.post("/api/partnerships/{partnership_id}/meetings")
def add_partner_meeting(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"] or not can_view_partnership(u,partnership_id): raise HTTPException(403,"Meeting permission denied")
    d=p.data
    if not d.get("meeting_date") or not d.get("meeting_type"): raise HTTPException(400,"Meeting date and type are required")
    mid=execute(insert(partner_meetings).values(partnership_id=partnership_id,opportunity_id=d.get("opportunity_id") or None,meeting_date=d["meeting_date"],meeting_time=d.get("meeting_time"),meeting_type=d["meeting_type"],status=d.get("status") or "Scheduled",purpose=d.get("purpose"),customer_participants=d.get("customer_participants"),jsan_participants=d.get("jsan_participants"),remarks=d.get("remarks"),created_by=u["id"]))
    execute(update(partnerships).where(partnerships.c.id==partnership_id).values(updated_at=utcnow())); audit(u["id"],"partner_meeting",mid,"CREATE",d); return row(select(partner_meetings).where(partner_meetings.c.id==mid))

@app.post("/api/partnerships/{partnership_id}/moms")
def add_partner_mom(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"] or not can_view_partnership(u,partnership_id): raise HTTPException(403,"MoM permission denied")
    d=p.data
    if not d.get("summary"): raise HTTPException(400,"Discussion summary is required")
    mid=execute(insert(partner_moms).values(meeting_id=d.get("meeting_id") or None,partnership_id=partnership_id,summary=d["summary"],customer_requirements=d.get("customer_requirements"),jsan_commitments=d.get("jsan_commitments"),customer_commitments=d.get("customer_commitments"),risks=d.get("risks"),next_steps=d.get("next_steps"),follow_up_date=d.get("follow_up_date"),created_by=u["id"]))
    if d.get("follow_up_date"): execute(update(partnerships).where(partnerships.c.id==partnership_id).values(next_follow_up=d["follow_up_date"],updated_at=utcnow()))
    audit(u["id"],"partner_mom",mid,"CREATE",d); return row(select(partner_moms).where(partner_moms.c.id==mid))

def _partner_mom_for(u,mom_id:int):
    m=row(select(partner_moms.c.id,partner_moms.c.partnership_id).where(partner_moms.c.id==mom_id))
    if not m or not can_view_partnership(u,m["partnership_id"]): raise HTTPException(404,"Minutes of Meeting not found")
    return m

@app.post("/api/partner-moms/{mom_id}/attachments")
def upload_partner_mom_attachment(mom_id:int,file:UploadFile=File(...),u=Depends(require_csrf)):
    if "MEETING_EDIT" not in u["permissions"]: raise HTTPException(403,"MoM permission denied")
    m=_partner_mom_for(u,mom_id)
    count=(row(select(func.count().label("n")).select_from(partner_mom_attachments).where(partner_mom_attachments.c.mom_id==mom_id)) or {}).get("n",0)
    if count>=MOM_ATTACHMENTS_PER_MOM: raise HTTPException(400,f"A MoM can have at most {MOM_ATTACHMENTS_PER_MOM} attachments")
    data=file.file.read(MOM_ATTACHMENT_MAX_BYTES+1)
    filename=_clean_filename(file.filename)
    _validate_docx(filename,data)
    digest=hashlib.sha256(data).hexdigest()
    aid=execute(insert(partner_mom_attachments).values(mom_id=mom_id,partnership_id=m["partnership_id"],filename=filename,content_type=DOCX_MIME,size_bytes=len(data),sha256=digest,data=data,uploaded_by=u["id"]))
    audit(u["id"],"partner_mom_attachment",aid,"CREATE",{"mom_id":mom_id,"filename":filename,"size_bytes":len(data),"sha256":digest})
    return {"id":aid,"mom_id":mom_id,"filename":filename,"size_bytes":len(data),"uploaded_by":u["id"],"uploaded_by_name":u["name"],"can_delete":True}

@app.get("/api/partner-moms/{mom_id}/attachments/{attachment_id}")
def download_partner_mom_attachment(mom_id:int,attachment_id:int,u=Depends(require_perm("LEAD_VIEW"))):
    _partner_mom_for(u,mom_id)
    a=row(select(partner_mom_attachments).where(and_(partner_mom_attachments.c.id==attachment_id,partner_mom_attachments.c.mom_id==mom_id)))
    if not a: raise HTTPException(404,"Attachment not found")
    from urllib.parse import quote
    ascii_name="".join(ch if ch.isascii() and ch.isprintable() and ch not in '"\\;' else "_" for ch in a["filename"])
    return Response(content=bytes(a["data"]),media_type=DOCX_MIME,headers={
        "Content-Disposition":f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(a['filename'])}",
        "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@app.delete("/api/partner-moms/{mom_id}/attachments/{attachment_id}")
def delete_partner_mom_attachment(mom_id:int,attachment_id:int,u=Depends(require_csrf)):
    _partner_mom_for(u,mom_id)
    a=row(select(partner_mom_attachments.c.id,partner_mom_attachments.c.filename,partner_mom_attachments.c.uploaded_by).where(and_(partner_mom_attachments.c.id==attachment_id,partner_mom_attachments.c.mom_id==mom_id)))
    if not a: raise HTTPException(404,"Attachment not found")
    if a["uploaded_by"]!=u["id"] and u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only the uploader, Super Admin or Admin can remove this file")
    execute(delete(partner_mom_attachments).where(partner_mom_attachments.c.id==attachment_id))
    audit(u["id"],"partner_mom_attachment",attachment_id,"DELETE",{"mom_id":mom_id,"filename":a["filename"]}); return {"ok":True}

@app.post("/api/partnerships/{partnership_id}/actions")
def add_partner_action(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if "ACTION_EDIT" not in u["permissions"] or not can_view_partnership(u,partnership_id): raise HTTPException(403,"Action permission denied")
    d=p.data; assigned=int(d.get("assigned_to") or u["id"])
    if not can_assign(u,assigned): raise HTTPException(403,"You cannot assign this action to that user")
    if not d.get("description") or not d.get("due_date"): raise HTTPException(400,"Action description and due date are required")
    aid=execute(insert(partner_actions).values(partnership_id=partnership_id,opportunity_id=d.get("opportunity_id") or None,action_date=d.get("action_date") or today_str(),description=d["description"],assigned_to=assigned,due_date=d["due_date"],status=d.get("status") or "Open",priority=d.get("priority") or "Medium",remarks=d.get("remarks"),created_by=u["id"]))
    execute(insert(notifications).values(user_id=assigned,notification_type="Action Assigned",title="New action assigned",message=d["description"],entity_type="partner_action",entity_id=aid,due_date=d["due_date"],severity="info")); audit(u["id"],"partner_action",aid,"CREATE",d); return row(select(partner_actions).where(partner_actions.c.id==aid))

@app.put("/api/partner-actions/{action_id}")
def update_partner_action(action_id:int,p:Payload,u=Depends(require_csrf)):
    a=row(select(partner_actions).where(partner_actions.c.id==action_id))
    if not a: raise HTTPException(404,"Action not found")
    if "ACTION_EDIT" not in u["permissions"] or (a["assigned_to"]!=u["id"] and not can_edit_partnership(u,a["partnership_id"])): raise HTTPException(403,"You cannot update this action")
    d=p.data; vals={k:d[k] for k in ("description","assigned_to","due_date","status","priority","remarks","completion_date") if k in d}
    if d.get("status")=="Completed" and not d.get("completion_date"): vals["completion_date"]=today_str()
    vals["updated_at"]=utcnow(); execute(update(partner_actions).where(partner_actions.c.id==action_id).values(**vals)); audit(u["id"],"partner_action",action_id,"UPDATE",d); return row(select(partner_actions).where(partner_actions.c.id==action_id))

@app.delete("/api/partner-actions/{action_id}")
def delete_partner_action(action_id:int,u=Depends(require_csrf)):
    if u["role"] not in ("Super Admin","Admin"): raise HTTPException(403,"Only Super Admin and Admin can delete actions")
    a=row(select(partner_actions).where(partner_actions.c.id==action_id))
    if not a: raise HTTPException(404,"Action not found")
    execute(delete(partner_actions).where(partner_actions.c.id==action_id))
    audit(u["id"],"partner_action",action_id,"DELETE",{"description":a["description"]}); return {"ok":True}

@app.get("/api/partner-opportunities/{opp_id}")
def partner_opportunity_detail(opp_id:int,u=Depends(require_perm("OPPORTUNITY_VIEW"))):
    if not can_view_partner_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    os_=[x for x in partner_opportunity_rows(u) if x["id"]==opp_id]
    if not os_: raise HTTPException(404,"Opportunity not found")
    fs=rows(select(partner_followups).where(partner_followups.c.opportunity_id==opp_id).order_by(partner_followups.c.follow_up_date.desc(),partner_followups.c.id.desc()))
    for f in fs: f["owner_name"]=user_name(f["owner_id"])
    tm=rows(select(partner_opportunity_team.c.user_id,partner_opportunity_team.c.team_role,users.c.name,roles.c.name.label("role")).select_from(partner_opportunity_team.join(users,users.c.id==partner_opportunity_team.c.user_id).join(roles,roles.c.id==users.c.role_id)).where(partner_opportunity_team.c.opportunity_id==opp_id))
    docs=rows(select(documents).where(and_(documents.c.entity_type=="partner_opportunity",documents.c.entity_id==opp_id)).order_by(documents.c.id.desc()))
    return {"opportunity":os_[0],"followups":fs,"team":tm,"documents":docs}

@app.post("/api/partnerships/{partnership_id}/opportunities")
def add_partner_opportunity(partnership_id:int,p:Payload,u=Depends(require_csrf)):
    if "OPPORTUNITY_EDIT" not in u["permissions"] or not can_view_partnership(u,partnership_id): raise HTTPException(403,"Opportunity permission denied")
    d=p.data; ensure_fields_editable(u,"opportunity",d); l=row(select(partnerships.c.company_id,partnerships.c.owner_id).where(partnerships.c.id==partnership_id)); owner=int(d.get("owner_id") or l["owner_id"])
    if not can_assign(u,owner): raise HTTPException(403,"You cannot assign this opportunity to that user")
    if not d.get("name"): raise HTTPException(400,"Opportunity name is required")
    status=d.get("status") or "New Opportunity"; validate_outcome(status,d); amount=float(d.get("amount") or 0); prob=float(d.get("probability") or 10); fc=d.get("forecast_category") or forecast_from_status(status)
    oid=execute(insert(partner_opportunities).values(partnership_id=partnership_id,company_id=l["company_id"],owner_id=owner,presales_owner_id=d.get("presales_owner_id") or None,name=d["name"],service_practice=d.get("service_practice"),status=status,forecast_category=fc,amount=amount,currency=d.get("currency") or "USD",probability=prob,weighted_value=amount*prob/100,expected_close_date=d.get("expected_close_date"),proposal_date=d.get("proposal_date"),last_follow_up_date=d.get("last_follow_up_date"),next_follow_up_date=d.get("next_follow_up_date"),follow_up_count=0,final_amount=d.get("final_amount"),lost_reason=d.get("lost_reason"),hold_reason=d.get("hold_reason"),hold_review_date=d.get("hold_review_date"),competitor=d.get("competitor"),remarks=d.get("remarks"),created_by=u["id"],closed_at=today_str() if status.startswith("Closed ") else None))
    if d.get("presales_owner_id"):
        execute(insert(partner_opportunity_team).values(opportunity_id=oid,user_id=int(d["presales_owner_id"]),team_role="Presales Owner",created_by=u["id"]))
    execute(update(partnerships).where(partnerships.c.id==partnership_id).values(status="Qualified",updated_at=utcnow())); audit(u["id"],"partner_opportunity",oid,"CREATE",d); return partner_opportunity_detail(oid,u)

@app.put("/api/partner-opportunities/{opp_id}")
def update_partner_opportunity(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_partner_opp(u,opp_id): raise HTTPException(403,"You cannot edit this opportunity")
    old=row(select(partner_opportunities).where(partner_opportunities.c.id==opp_id)); d=p.data; ensure_fields_editable(u,"opportunity",d)
    if "owner_id" in d and int(d["owner_id"]) != int(old["owner_id"]):
        if not can_assign(u, int(d["owner_id"])): raise HTTPException(403,"You cannot assign this opportunity to that user")
    merged={**old,**d}; status=merged["status"]
    if status.startswith("Closed ") and "OPPORTUNITY_CLOSE" not in u["permissions"]: raise HTTPException(403,"Opportunity-close permission required")
    validate_outcome(status,merged)
    vals={k:d[k] for k in ("owner_id","presales_owner_id","name","service_practice","status","forecast_category","amount","currency","probability","expected_close_date","proposal_date","last_follow_up_date","next_follow_up_date","final_amount","lost_reason","hold_reason","hold_review_date","competitor","remarks") if k in d}
    amount=float(vals.get("amount",old["amount"]) or 0); prob=float(vals.get("probability",old["probability"]) or 0); vals["weighted_value"]=amount*prob/100
    if "forecast_category" not in d and "status" in d: vals["forecast_category"]=forecast_from_status(status)
    vals["closed_at"]=today_str() if status.startswith("Closed ") else None; vals["updated_at"]=utcnow(); execute(update(partner_opportunities).where(partner_opportunities.c.id==opp_id).values(**vals))
    if d.get("presales_owner_id"):
        pid=int(d["presales_owner_id"])
        if not row(select(partner_opportunity_team.c.opportunity_id).where(and_(partner_opportunity_team.c.opportunity_id==opp_id,partner_opportunity_team.c.user_id==pid))): execute(insert(partner_opportunity_team).values(opportunity_id=opp_id,user_id=pid,team_role="Presales Owner",created_by=u["id"]))
    audit(u["id"],"partner_opportunity",opp_id,"UPDATE",d); return partner_opportunity_detail(opp_id,u)

@app.post("/api/partner-opportunities/{opp_id}/followups")
def add_partner_followup(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_partner_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    d=p.data; fd=d.get("follow_up_date") or today_str(); oid=int(d.get("owner_id") or u["id"])
    fid=execute(insert(partner_followups).values(opportunity_id=opp_id,follow_up_date=fd,owner_id=oid,response=d.get("response"),next_follow_up_date=d.get("next_follow_up_date"),remarks=d.get("remarks"),created_by=u["id"]))
    old=row(select(partner_opportunities.c.follow_up_count).where(partner_opportunities.c.id==opp_id)); execute(update(partner_opportunities).where(partner_opportunities.c.id==opp_id).values(last_follow_up_date=fd,next_follow_up_date=d.get("next_follow_up_date"),follow_up_count=(old["follow_up_count"] or 0)+1,updated_at=utcnow())); audit(u["id"],"partner_followup",fid,"CREATE",d); return partner_opportunity_detail(opp_id,u)

@app.post("/api/partner-opportunities/{opp_id}/team")
def add_partner_team_member(opp_id:int,p:Payload,u=Depends(require_csrf)):
    if not can_edit_partner_opp(u,opp_id): raise HTTPException(403,"Opportunity access denied")
    uid=int(p.data["user_id"]); role=p.data.get("team_role") or "Contributor"
    if not can_assign(u,uid): raise HTTPException(403,"You cannot add that user to this opportunity team")
    with engine.begin() as c:
        ex=c.execute(select(partner_opportunity_team.c.opportunity_id).where(and_(partner_opportunity_team.c.opportunity_id==opp_id,partner_opportunity_team.c.user_id==uid))).fetchone()
        if ex: c.execute(update(partner_opportunity_team).where(and_(partner_opportunity_team.c.opportunity_id==opp_id,partner_opportunity_team.c.user_id==uid)).values(team_role=role))
        else: c.execute(insert(partner_opportunity_team).values(opportunity_id=opp_id,user_id=uid,team_role=role,created_by=u["id"]))
    audit(u["id"],"partner_opportunity",opp_id,"TEAM_UPDATE",p.data); return partner_opportunity_detail(opp_id,u)

@app.get("/api/query/partner-companies")
def query_partner_companies(q:str="",vertical:str="",region:str="",page:int=1,page_size:int=25,u=Depends(require_perm("COMPANY_VIEW"))):
    page=max(1,page); page_size=min(max(1,page_size),100)
    contact_count=select(func.count(partner_contacts.c.id)).where(and_(partner_contacts.c.company_id==partner_companies.c.id,partner_contacts.c.active==True)).correlate(partner_companies).scalar_subquery()
    lead_count=select(func.count(partnerships.c.id)).where(partnerships.c.company_id==partner_companies.c.id).correlate(partner_companies).scalar_subquery()
    opp_count=select(func.count(partner_opportunities.c.id)).where(partner_opportunities.c.company_id==partner_companies.c.id).correlate(partner_companies).scalar_subquery()
    stmt=select(partner_companies,contact_count.label("contact_count"),lead_count.label("lead_count"),opp_count.label("opportunity_count")).where(partner_companies.c.status!="Merged")
    filters=[]
    if q: filters.append(or_(func.lower(partner_companies.c.name).like(f"%{q.lower()}%"),func.lower(func.coalesce(partner_companies.c.website," ")).like(f"%{q.lower()}%"),func.lower(func.coalesce(partner_companies.c.vertical," ")).like(f"%{q.lower()}%")))
    if vertical: filters.append(func.lower(partner_companies.c.vertical).like(f"%{vertical.lower()}%"))
    if region: filters.append(partner_companies.c.region==region)
    if filters: stmt=stmt.where(*filters)
    total_stmt=select(func.count()).select_from(select(partner_companies.c.id).where(partner_companies.c.status!="Merged",*filters).subquery())
    n=row(total_stmt); n=list(n.values())[0] if n else 0
    items=rows(stmt.order_by(partner_companies.c.name).offset((page-1)*page_size).limit(page_size))
    return {"items":items,"page":page,"page_size":page_size,"total":n,"pages":(n+page_size-1)//page_size}

@app.get("/api/query/partnerships")
def query_partnerships(q:str="",status:str="",temperature:str="",owner_id:int|None=None,region:str="",followup:str="",sort:str="",dir:str="asc",page:int=1,page_size:int=25,u=Depends(require_perm("LEAD_VIEW"))):
    page=max(1,page); page_size=min(max(1,page_size),100); powner=users.alias("qpowner")
    primary=select(partner_contacts.c.name).where(and_(partner_contacts.c.company_id==partnerships.c.company_id,partner_contacts.c.active==True)).order_by(partner_contacts.c.is_primary.desc(),partner_contacts.c.id).limit(1).correlate(partnerships).scalar_subquery()
    joined=partnerships.join(partner_companies,partner_companies.c.id==partnerships.c.company_id).join(powner,powner.c.id==partnerships.c.owner_id)
    base=select(partnerships,partner_companies.c.name.label("company_name"),partner_companies.c.vertical,powner.c.name.label("owner_name"),primary.label("primary_contact")).select_from(joined).where(partnership_visibility_condition(u))
    common=[]
    if q: common.append(or_(func.lower(partner_companies.c.name).like(f"%{q.lower()}%"),func.lower(func.coalesce(partnerships.c.remarks," ")).like(f"%{q.lower()}%"),func.lower(powner.c.name).like(f"%{q.lower()}%")))
    if status: common.append(partnerships.c.status==status)
    if owner_id: common.append(partnerships.c.owner_id==owner_id)
    if region=="__none__": common.append(or_(partnerships.c.region.is_(None),partnerships.c.region==""))
    elif region: common.append(partnerships.c.region==region)
    t=today_str(); week=(date.today()+timedelta(days=7)).isoformat()
    if followup=="overdue": common.append(and_(partnerships.c.next_follow_up.is_not(None),partnerships.c.next_follow_up!="",partnerships.c.next_follow_up<t))
    elif followup=="today": common.append(partnerships.c.next_follow_up==t)
    elif followup=="week": common.append(and_(partnerships.c.next_follow_up>=t,partnerships.c.next_follow_up<=week))
    elif followup=="none": common.append(or_(partnerships.c.next_follow_up.is_(None),partnerships.c.next_follow_up==""))
    elif followup: common.append(partnerships.c.next_follow_up==followup)
    facet_rows=rows(select(partnerships.c.region,partnerships.c.owner_id,powner.c.name.label("owner_name"),partnerships.c.temperature,partnerships.c.status,partnerships.c.next_follow_up).select_from(joined).where(partnership_visibility_condition(u)).distinct())
    distinct=lambda k:{r[k] for r in facet_rows if r[k]}
    temp_order={"Hot":0,"Warm":1,"Cold":2}
    facets={"temperatures":sorted(distinct("temperature"),key=lambda v:(temp_order.get(v,9),v)),
            "statuses":sorted(distinct("status"),key=str.lower),
            "follow_ups":sorted(distinct("next_follow_up")),
            "has_empty_follow_up":any(not r["next_follow_up"] for r in facet_rows),
            "regions":sorted(distinct("region"),key=str.lower),
            "has_empty_region":any(not r["region"] for r in facet_rows),
            "owners":sorted([{"id":oid,"name":n} for oid,n in {(r["owner_id"],r["owner_name"]) for r in facet_rows}],key=lambda x:(x["name"] or "").lower())}
    if common: base=base.where(*common)
    summary_stmt=select(partnerships.c.temperature,func.count(partnerships.c.id).label("count")).select_from(partnerships.join(partner_companies,partner_companies.c.id==partnerships.c.company_id).join(powner,powner.c.id==partnerships.c.owner_id)).where(partnership_visibility_condition(u),*common).group_by(partnerships.c.temperature)
    temp_counts={r["temperature"]:r["count"] for r in rows(summary_stmt)}
    overdue_stmt=select(func.count(partnerships.c.id).label("count")).select_from(partnerships.join(partner_companies,partner_companies.c.id==partnerships.c.company_id).join(powner,powner.c.id==partnerships.c.owner_id)).where(partnership_visibility_condition(u),*common,partnerships.c.next_follow_up.is_not(None),partnerships.c.next_follow_up<today_str(),~partnerships.c.status.in_(["Converted","Disqualified","Lost"]))
    overdue=(row(overdue_stmt) or {}).get("count",0)
    if temperature: base=base.where(partnerships.c.temperature==temperature)
    nrow=row(select(func.count().label("total")).select_from(base.subquery())); n=int((nrow or {}).get("total",0))
    temp_rank=case((partnerships.c.temperature=="Hot",0),(partnerships.c.temperature=="Warm",1),(partnerships.c.temperature=="Cold",2),else_=3)
    sort_cols={"company_name":func.lower(partner_companies.c.name),"temperature":temp_rank,"status":func.lower(partnerships.c.status),
               "owner_name":func.lower(powner.c.name),"next_follow_up":partnerships.c.next_follow_up,"region":func.lower(func.coalesce(partnerships.c.region,""))}
    order=[]
    if sort in sort_cols:
        col=sort_cols[sort]
        if sort in ("next_follow_up","region"):
            empty=or_(partnerships.c.next_follow_up.is_(None),partnerships.c.next_follow_up=="") if sort=="next_follow_up" else or_(partnerships.c.region.is_(None),partnerships.c.region=="")
            order.append(case((empty,1),else_=0))
        order.append(col.desc() if dir=="desc" else col.asc())
    order.append(partnerships.c.updated_at.desc())
    items=rows(base.order_by(*order).offset((page-1)*page_size).limit(page_size))
    if "LEAD_EDIT" in u["permissions"] and items:
        scope=set(scope_user_ids(u))
        shared_edit={r["entity_id"] for r in rows(select(record_shares.c.entity_id).where(and_(record_shares.c.entity_type=="partnership",record_shares.c.user_id==u["id"],record_shares.c.access_level=="edit",record_shares.c.entity_id.in_([i["id"] for i in items]))))}
        for i in items: i["can_edit"]=i["owner_id"] in scope or i["id"] in shared_edit
    else:
        for i in items: i["can_edit"]=False
    return {"items":items,"page":page,"page_size":page_size,"total":n,"pages":(n+page_size-1)//page_size,"facets":facets,"summary":{"hot":temp_counts.get("Hot",0),"warm":temp_counts.get("Warm",0),"cold":temp_counts.get("Cold",0),"overdue_followups":overdue}}

# ── Partnerships CSV import (same behaviour as the Prospects CSV import) ──────
PARTNERSHIP_SAMPLE_CSV_HEADER = "Company,Vertical,Region,Country,Contact Name,Designation,Email,Phone,Signal,Source,Status,Next Follow-up,Remarks,Owner Email"
PARTNERSHIP_SAMPLE_CSV_ROWS = [
    "Meridian Systems Alliance,Systems Integration,North America,USA,Pat Rivera,VP Alliances,pat@meridian.example,+1-555-0140,Warm,Referral,New,2026-10-20,Exploring a co-sell agreement,bd.exec1@jsan.local",
    "Northlight Analytics Partners,Data & AI,Europe,UK,Sam Cole,Director Partnerships,sam@northlight.example,+44-20-5678,Hot,Event,Engaged,2026-10-12,Signed NDA; drafting partnership terms,bd.exec2@jsan.local",
]

@app.get("/api/partnerships/import/sample")
def download_partnership_sample_csv(u=Depends(require_perm("LEAD_CREATE"))):
    content = PARTNERSHIP_SAMPLE_CSV_HEADER + "\n" + "\n".join(PARTNERSHIP_SAMPLE_CSV_ROWS) + "\n"
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=pursuitnova_partnerships_sample.csv"})

@app.post("/api/partnerships/import")
def import_partnerships_csv(file: UploadFile = File(...), u=Depends(require_csrf)):
    if "LEAD_CREATE" not in u.get("permissions", []): raise HTTPException(403, "Lead create permission required")
    try:
        raw = file.file.read()
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try: text = raw.decode(enc); break
            except Exception: continue
        else: raise ValueError("Unable to decode file")
        reader = csv.DictReader(io.StringIO(text))
    except Exception as e:
        raise HTTPException(400, f"Cannot read CSV: {e}")

    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    required = {"company"}
    missing_cols = required - {f.replace(" ", "").replace("_", "") for f in fields}
    if missing_cols:
        raise HTTPException(400, f"Missing required column(s): {', '.join(required)}. Found: {', '.join(reader.fieldnames or [])}")

    user_cache = {}; user_names = {}
    for ur in rows(select(users.c.id, users.c.name, users.c.email)):
        user_cache[ur["email"].lower()] = ur["id"]
        user_cache[ur["name"].lower()] = ur["id"]
        user_names[ur["id"]] = ur["name"]
    assignable_cache = {}

    results = {"imported": 0, "skipped": 0, "errors": [], "warnings": []}

    for idx, raw_row in enumerate(reader, start=2):
        row_num = idx
        r = {k.strip().lower().replace(" ", "_"): (v.strip() if v else "") for k, v in raw_row.items() if k}
        company_name = r.get("company", "").strip()
        if not company_name:
            results["errors"].append({"row": row_num, "message": "Company name is empty — row skipped"})
            results["skipped"] += 1
            continue

        owner_key = (r.get("owner_email") or r.get("owner") or "").strip().lower()
        owner_id = user_cache.get(owner_key, u["id"])
        if owner_key and owner_key not in user_cache:
            results["warnings"].append({"row": row_num, "message": f"Owner '{r.get('owner_email') or r.get('owner')}' not found — assigned to you"})
        elif owner_id != u["id"]:
            if owner_id not in assignable_cache: assignable_cache[owner_id] = can_assign(u, owner_id)
            if not assignable_cache[owner_id]:
                results["warnings"].append({"row": row_num, "message": f"You cannot assign partnerships to {user_names.get(owner_id, 'that user')} — assigned to you"})
                owner_id = u["id"]

        raw_status = (r.get("status") or "New").strip()
        status = STATUS_MAP.get(raw_status.lower(), raw_status)
        if status not in VALID_STATUSES:
            results["warnings"].append({"row": row_num, "message": f"Unknown status '{raw_status}' — defaulted to 'New'"})
            status = "New"

        signal = (r.get("signal") or r.get("temperature") or "Warm").strip().title()
        if signal not in VALID_SIGNALS:
            results["warnings"].append({"row": row_num, "message": f"Unknown signal '{signal}' — defaulted to 'Warm'"})
            signal = "Warm"

        norm = normalize_name(company_name)
        existing_company = row(select(partner_companies.c.id, partner_companies.c.name).where(partner_companies.c.normalized_name == norm)) if norm else None

        try:
            if existing_company:
                company_id = existing_company["id"]
                results["warnings"].append({"row": row_num, "message": f"Company '{company_name}' already exists — linked to existing"})
            else:
                company_id = execute(insert(partner_companies).values(
                    name=company_name, normalized_name=norm,
                    vertical=classify_vertical(r.get("vertical")) or "Other",
                    website=r.get("website") or None, domain=domain_from_url(r.get("website")),
                    region=r.get("region") or None, country=r.get("country") or None,
                    state=r.get("state") or None, city=r.get("city") or None,
                    status="Active", created_by=u["id"]
                ))

            existing_partnership = row(select(partnerships.c.id).where(partnerships.c.company_id == company_id))
            if existing_partnership:
                results["warnings"].append({"row": row_num, "message": f"Partnership for '{company_name}' already exists — skipped"})
                results["skipped"] += 1
                continue

            next_fu = None
            raw_fu = r.get("next_follow-up") or r.get("next_follow_up") or r.get("next_action_date") or ""
            if raw_fu:
                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
                    try: next_fu = datetime.strptime(raw_fu, fmt).strftime("%Y-%m-%d"); break
                    except Exception: pass

            source = r.get("source") or "Other"
            remarks = r.get("remarks") or r.get("received_summary") or r.get("next_action") or ""

            partnership_id = execute(insert(partnerships).values(
                company_id=company_id, owner_id=owner_id,
                temperature=signal, source=source, status=status,
                region=r.get("region") or None, country=r.get("country") or None,
                next_follow_up=next_fu, remarks=remarks, created_by=u["id"]
            ))

            contact_name = r.get("contact_name") or r.get("contact") or ""
            if contact_name:
                emails = [e.strip() for e in (r.get("email") or "").split(";") if e.strip() and "@" in e]
                primary_email = emails[0] if emails else None
                ne = normalize_email(primary_email)
                execute(insert(partner_contacts).values(
                    company_id=company_id, name=contact_name,
                    designation=r.get("designation") or None,
                    email=primary_email, normalized_email=ne,
                    phone=r.get("phone") or None,
                    is_primary=True, active=True, created_by=u["id"]
                ))
                for extra_email in emails[1:]:
                    ene = normalize_email(extra_email)
                    if ene and not row(select(partner_contacts.c.id).where(and_(partner_contacts.c.company_id == company_id, partner_contacts.c.normalized_email == ene))):
                        execute(insert(partner_contacts).values(
                            company_id=company_id, name=extra_email.split("@")[0],
                            email=extra_email, normalized_email=ene,
                            is_primary=False, active=True, created_by=u["id"]
                        ))

            action_desc = r.get("next_action") or r.get("sent_subject") or None
            if action_desc and partnership_id:
                execute(insert(partner_actions).values(
                    partnership_id=partnership_id, action_date=today_str(),
                    description=action_desc, assigned_to=owner_id,
                    due_date=next_fu or (date.today() + timedelta(days=7)).isoformat(),
                    status="Open", priority="Medium", created_by=u["id"]
                ))

            audit(u["id"], "partnership", partnership_id, "IMPORT", {"company": company_name, "source": "csv"})
            results["imported"] += 1

        except IntegrityError as e:
            results["errors"].append({"row": row_num, "message": f"Database error: {str(e)[:100]}"})
            results["skipped"] += 1
        except Exception as e:
            results["errors"].append({"row": row_num, "message": str(e)[:150]})
            results["skipped"] += 1

    return results

@app.get("/api/vendor-targets")
def list_vendor_targets(u=Depends(require_perm("COMPANY_VIEW"))):
    return {"items": rows(select(vendor_targets, users.c.name.label("owner_name")).select_from(vendor_targets.outerjoin(users, users.c.id == vendor_targets.c.owner_id)).order_by(vendor_targets.c.company_name)), "statuses": VENDOR_REGISTRATION_STATUSES}

@app.post("/api/vendor-targets")
def create_vendor_target(p: Payload, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    d = p.data
    name = _clean_text(d.get("company_name"), 220)
    if not name: raise HTTPException(400, "Company name is required")
    status = d.get("registration_status") or "Ready to initiate"
    if status not in VENDOR_REGISTRATION_STATUSES: raise HTTPException(400, "Invalid registration status")
    vid = execute(insert(vendor_targets).values(
        company_name=name, market=_clean_text(d.get("market"), 120), public_evidence=_clean_text(d.get("public_evidence")),
        entry_route=_clean_text(d.get("entry_route"), 220), suggested_approach=_clean_text(d.get("suggested_approach")),
        registration_status=status, notes=_clean_text(d.get("notes")),
        owner_id=int(d["owner_id"]) if d.get("owner_id") else None, created_by=u["id"]))
    audit(u["id"], "vendor_target", vid, "CREATE", d)
    return row(select(vendor_targets).where(vendor_targets.c.id == vid))

@app.put("/api/vendor-targets/{target_id}")
def update_vendor_target(target_id: int, p: Payload, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    if not row(select(vendor_targets.c.id).where(vendor_targets.c.id == target_id)): raise HTTPException(404, "Target not found")
    d = p.data
    vals = {k: d[k] for k in ("company_name", "market", "public_evidence", "entry_route", "suggested_approach", "registration_status", "notes", "owner_id") if k in d}
    if "company_name" in vals:
        vals["company_name"] = _clean_text(vals["company_name"], 220)
        if not vals["company_name"]: raise HTTPException(400, "Company name is required")
    if "registration_status" in vals and vals["registration_status"] not in VENDOR_REGISTRATION_STATUSES: raise HTTPException(400, "Invalid registration status")
    for k, n in (("market", 120), ("entry_route", 220), ("public_evidence", None), ("suggested_approach", None), ("notes", None)):
        if k in vals: vals[k] = _clean_text(vals[k], n)
    if "owner_id" in vals: vals["owner_id"] = int(vals["owner_id"]) if vals["owner_id"] else None
    vals["updated_at"] = utcnow()
    execute(update(vendor_targets).where(vendor_targets.c.id == target_id).values(**vals))
    audit(u["id"], "vendor_target", target_id, "UPDATE", d)
    return row(select(vendor_targets).where(vendor_targets.c.id == target_id))

@app.delete("/api/vendor-targets/{target_id}")
def delete_vendor_target(target_id: int, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    t = row(select(vendor_targets.c.id, vendor_targets.c.company_name).where(vendor_targets.c.id == target_id))
    if not t: raise HTTPException(404, "Target not found")
    execute(delete(vendor_targets).where(vendor_targets.c.id == target_id))
    audit(u["id"], "vendor_target", target_id, "DELETE", {"company_name": t["company_name"]})
    return {"ok": True}

# ── RFP (tender) tracking ───────────────────────────────────────────────────────────────────────
# Additive feature on its own two tables (rfps, rfp_documents). Viewing follows COMPANY_VIEW and
# editing COMPANY_EDIT, exactly like the Supplier Network; no existing table, route or rule changes.
# Every COMPANY_VIEW login can preview an uploaded document in-page; only RFP_DOWNLOAD_EMAIL gets
# the explicit Download action (the "can_download" flag drives that in the UI).
def _rfp_can_download(u) -> bool:
    return (u.get("email") or "").strip().lower() == RFP_DOWNLOAD_EMAIL

def _rfp_document_category(value) -> str:
    c = (value or "general").strip().lower()
    if c not in RFP_DOCUMENT_CATEGORIES: raise HTTPException(400, "Invalid document category")
    return c

def _rfp_or_404(rfp_id: int):
    r = row(select(rfps.c.id, rfps.c.name).where(rfps.c.id == rfp_id))
    if not r: raise HTTPException(404, "RFP not found")
    return r

def _clean_rfp_date(v, label):
    t = _clean_text(v, 10)
    if t and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t): raise HTTPException(400, f"{label} must be a date in YYYY-MM-DD format")
    return t

def _rfp_status(value, label):
    s = value or "Initiated"
    if s not in RFP_STATUSES: raise HTTPException(400, f"Invalid {label}")
    return s

def _rfp_qa_status(value):
    s = value or "Not started"
    if s not in RFP_QA_STATUSES: raise HTTPException(400, "Invalid Q&A status")
    return s

def _rfp_documents(rfp_id: int, u):
    out = []
    for d in rows(select(rfp_documents.c.id, rfp_documents.c.filename, rfp_documents.c.size_bytes, rfp_documents.c.category, rfp_documents.c.content_type,
                         rfp_documents.c.created_at, rfp_documents.c.uploaded_by, users.c.name.label("uploaded_by_name"))
                  .select_from(rfp_documents.outerjoin(users, users.c.id == rfp_documents.c.uploaded_by))
                  .where(rfp_documents.c.rfp_id == rfp_id).order_by(rfp_documents.c.id)):
        d["can_delete"] = (d["uploaded_by"] == u["id"]) or is_admin_role(u)
        out.append(d)
    return out

@app.get("/api/rfps")
def list_rfps(u=Depends(require_perm("COMPANY_VIEW"))):
    items = rows(select(rfps, users.c.name.label("created_by_name"))
                 .select_from(rfps.outerjoin(users, users.c.id == rfps.c.created_by))
                 .order_by(rfps.c.id.desc()))
    ids = [it["id"] for it in items]
    docs_by_rfp = defaultdict(list)
    if ids:
        for d in rows(select(rfp_documents.c.id, rfp_documents.c.rfp_id, rfp_documents.c.filename, rfp_documents.c.size_bytes, rfp_documents.c.category, rfp_documents.c.content_type,
                             rfp_documents.c.created_at, rfp_documents.c.uploaded_by, users.c.name.label("uploaded_by_name"))
                      .select_from(rfp_documents.outerjoin(users, users.c.id == rfp_documents.c.uploaded_by))
                      .where(rfp_documents.c.rfp_id.in_(ids)).order_by(rfp_documents.c.id)):
            d["can_delete"] = (d["uploaded_by"] == u["id"]) or is_admin_role(u)
            docs_by_rfp[d["rfp_id"]].append(d)
    for it in items:
        it["documents"] = docs_by_rfp.get(it["id"], [])
        it["document_count"] = len(it["documents"])
    return {"items": items, "statuses": RFP_STATUSES, "qa_statuses": RFP_QA_STATUSES, "can_download": _rfp_can_download(u)}

@app.post("/api/rfps")
def create_rfp(p: Payload, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    d = p.data
    name = _clean_text(d.get("name"), 220)
    if not name: raise HTTPException(400, "RFP name is required")
    rid = execute(insert(rfps).values(
        name=name, description=_clean_text(d.get("description")),
        rfp_date=_clean_rfp_date(d.get("rfp_date"), "Date of RFP"), submission_eta=_clean_rfp_date(d.get("submission_eta"), "Submission ETA"),
        qa_timeline=_clean_text(d.get("qa_timeline")), qa_status=_rfp_qa_status(d.get("qa_status")),
        technical_response=_clean_text(d.get("technical_response")), pricing=_clean_text(d.get("pricing")),
        jsan_status=_rfp_status(d.get("jsan_status"), "JSAN participation status"), vendor_status=_rfp_status(d.get("vendor_status"), "vendor participation status"),
        created_by=u["id"]))
    audit(u["id"], "rfp", rid, "CREATE", d)
    return row(select(rfps).where(rfps.c.id == rid))

@app.put("/api/rfps/{rfp_id}")
def update_rfp(rfp_id: int, p: Payload, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    _rfp_or_404(rfp_id)
    d = p.data
    vals = {k: d[k] for k in ("name", "description", "rfp_date", "submission_eta", "qa_timeline", "qa_status", "technical_response", "pricing", "jsan_status", "vendor_status") if k in d}
    if "name" in vals:
        vals["name"] = _clean_text(vals["name"], 220)
        if not vals["name"]: raise HTTPException(400, "RFP name is required")
    for k in ("description", "qa_timeline", "technical_response", "pricing"):
        if k in vals: vals[k] = _clean_text(vals[k])
    if "rfp_date" in vals: vals["rfp_date"] = _clean_rfp_date(vals["rfp_date"], "Date of RFP")
    if "submission_eta" in vals: vals["submission_eta"] = _clean_rfp_date(vals["submission_eta"], "Submission ETA")
    if "qa_status" in vals: vals["qa_status"] = _rfp_qa_status(vals["qa_status"])
    if "jsan_status" in vals: vals["jsan_status"] = _rfp_status(vals["jsan_status"], "JSAN participation status")
    if "vendor_status" in vals: vals["vendor_status"] = _rfp_status(vals["vendor_status"], "vendor participation status")
    vals["updated_at"] = utcnow()
    execute(update(rfps).where(rfps.c.id == rfp_id).values(**vals))
    audit(u["id"], "rfp", rfp_id, "UPDATE", d)
    return row(select(rfps).where(rfps.c.id == rfp_id))

@app.delete("/api/rfps/{rfp_id}")
def delete_rfp(rfp_id: int, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    r = _rfp_or_404(rfp_id)
    execute(delete(rfp_documents).where(rfp_documents.c.rfp_id == rfp_id))  # explicit: SQLite does not enforce ON DELETE CASCADE by default
    execute(delete(rfps).where(rfps.c.id == rfp_id))
    audit(u["id"], "rfp", rfp_id, "DELETE", {"name": r["name"]})
    return {"ok": True}

@app.post("/api/rfps/{rfp_id}/attachments")
def upload_rfp_document(rfp_id: int, file: UploadFile = File(...), category: str = Form("general"), u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    _rfp_or_404(rfp_id)
    cat = _rfp_document_category(category)
    count = (row(select(func.count().label("n")).select_from(rfp_documents).where(rfp_documents.c.rfp_id == rfp_id)) or {}).get("n", 0)
    if count >= RFP_DOCUMENTS_PER_RFP: raise HTTPException(400, f"An RFP can have at most {RFP_DOCUMENTS_PER_RFP} documents")
    data = file.file.read(MOM_ATTACHMENT_MAX_BYTES + 1)
    filename = _clean_filename(file.filename)
    content_type = _validate_rfp_file(filename, data)
    digest = hashlib.sha256(data).hexdigest()
    did = execute(insert(rfp_documents).values(rfp_id=rfp_id, filename=filename, content_type=content_type, size_bytes=len(data), sha256=digest, data=data, category=cat, uploaded_by=u["id"]))
    audit(u["id"], "rfp_document", did, "CREATE", {"rfp_id": rfp_id, "filename": filename, "size_bytes": len(data), "sha256": digest, "category": cat})
    return {"id": did, "rfp_id": rfp_id, "filename": filename, "size_bytes": len(data), "category": cat, "uploaded_by": u["id"], "uploaded_by_name": u["name"], "can_delete": True}

@app.get("/api/rfps/{rfp_id}/attachments/{doc_id}")
def view_rfp_document(rfp_id: int, doc_id: int, u=Depends(require_perm("COMPANY_VIEW"))):
    # Every viewer may open the in-page preview; the actual save-to-disk affordance in the UI is
    # shown only to the authorised custodian (u["can_download"]/can_download on the list response).
    _rfp_or_404(rfp_id)
    a = row(select(rfp_documents).where(and_(rfp_documents.c.id == doc_id, rfp_documents.c.rfp_id == rfp_id)))
    if not a: raise HTTPException(404, "Document not found")
    from urllib.parse import quote
    ascii_name = "".join(ch if ch.isascii() and ch.isprintable() and ch not in '"\\;' else "_" for ch in a["filename"])
    disposition = "attachment" if _rfp_can_download(u) else "inline"
    audit(u["id"], "rfp_document", doc_id, "DOWNLOAD" if _rfp_can_download(u) else "VIEW", {"rfp_id": rfp_id, "filename": a["filename"]})
    return Response(content=bytes(a["data"]), media_type=a["content_type"] or DOCX_MIME, headers={
        "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(a['filename'])}",
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@app.delete("/api/rfps/{rfp_id}/attachments/{doc_id}")
def delete_rfp_document(rfp_id: int, doc_id: int, u=Depends(require_csrf)):
    if "COMPANY_EDIT" not in u["permissions"]: raise HTTPException(403, "Company edit permission required")
    _rfp_or_404(rfp_id)
    a = row(select(rfp_documents.c.id, rfp_documents.c.filename, rfp_documents.c.uploaded_by).where(and_(rfp_documents.c.id == doc_id, rfp_documents.c.rfp_id == rfp_id)))
    if not a: raise HTTPException(404, "Document not found")
    if a["uploaded_by"] != u["id"] and not is_admin_role(u): raise HTTPException(403, "Only the uploader, Super Admin or Admin can remove this file")
    execute(delete(rfp_documents).where(rfp_documents.c.id == doc_id))
    audit(u["id"], "rfp_document", doc_id, "DELETE", {"rfp_id": rfp_id, "filename": a["filename"]})
    return {"ok": True}

# Static no-build PWA UI. API routes are registered first, so /api remains authoritative.
STATIC_DIR=os.getenv("FRONTEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..","frontend","dist"))
if os.path.isdir(STATIC_DIR):
    app.mount("/",StaticFiles(directory=STATIC_DIR,html=True),name="ui")
