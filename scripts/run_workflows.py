"""Run notification/workflow evaluation for all active users. Schedule hourly in production until a durable worker is introduced."""
from app.db import rows, users, select
from app.main import safe_user, run_workflows_for_user

for r in rows(select(users.c.id).where(users.c.active == True)):
    u = safe_user(r["id"])
    if u:
        run_workflows_for_user(u)
print("PursuitNova workflow evaluation completed.")
