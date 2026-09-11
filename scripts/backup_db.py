#!/usr/bin/env python3
import os, sys, sqlite3, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
url=os.getenv('DATABASE_URL','sqlite:///./data/pursuitnova.db')
out=Path(os.getenv('BACKUP_DIR','./backups')); out.mkdir(parents=True,exist_ok=True)
ts=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
if url.startswith('sqlite:///'):
    src=Path(url.replace('sqlite:///','',1)); src=src if src.is_absolute() else Path.cwd()/src
    if not src.exists(): sys.exit(f'Database not found: {src}')
    dest=out/f'pursuitnova_{ts}.sqlite3'
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d: s.backup(d)
    print(dest)
elif url.startswith('postgresql'):
    if not shutil.which('pg_dump'): sys.exit('pg_dump is required for PostgreSQL backup')
    dest=out/f'pursuitnova_{ts}.dump'
    subprocess.run(['pg_dump','--format=custom','--file',str(dest),url],check=True)
    print(dest)
else: sys.exit('Unsupported DATABASE_URL')
