"""Create the first Super Admin in a non-demo database.
Usage (from backend):
  ADMIN_NAME='Name' ADMIN_EMAIL='admin@company.com' ADMIN_PASSWORD='...' PYTHONPATH=. python ../scripts/bootstrap_admin.py
"""
import os
from sqlalchemy import select, insert
from app.db import init_db, row, execute, roles, users, hash_password

init_db(seed_demo=False)
name=os.environ.get('ADMIN_NAME','PursuitNova Super Admin')
email=os.environ.get('ADMIN_EMAIL')
password=os.environ.get('ADMIN_PASSWORD')
if not email or not password:
    raise SystemExit('ADMIN_EMAIL and ADMIN_PASSWORD are required')
if row(select(users.c.id).where(users.c.email==email.lower())):
    raise SystemExit('User already exists')
r=row(select(roles.c.id).where(roles.c.name=='Super Admin'))
uid=execute(insert(users).values(name=name,email=email.lower(),password_hash=hash_password(password),role_id=r['id'],title='Platform Owner',region='Global',active=True))
print(f'Created Super Admin user id={uid} email={email}')
