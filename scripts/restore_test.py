#!/usr/bin/env python3
import os, sys, sqlite3, subprocess, shutil, tempfile
from pathlib import Path
if len(sys.argv)<2: sys.exit('Usage: restore_test.py <backup-file>')
b=Path(sys.argv[1]);
if not b.exists(): sys.exit('Backup not found')
if b.suffix in {'.sqlite3','.db'}:
    tmp=Path(tempfile.gettempdir())/'pursuitnova_restore_test.sqlite3'
    if tmp.exists(): tmp.unlink()
    with sqlite3.connect(b) as s, sqlite3.connect(tmp) as d: s.backup(d)
    with sqlite3.connect(tmp) as c:
        result=c.execute('PRAGMA integrity_check').fetchone()[0]
        tables=c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    if result!='ok' or tables<10: sys.exit(f'Restore failed: integrity={result}, tables={tables}')
    print(f'PASS sqlite restore integrity={result} tables={tables}')
    tmp.unlink(missing_ok=True)
elif b.suffix=='.dump':
    target=os.getenv('RESTORE_TEST_DATABASE_URL')
    if not target: sys.exit('RESTORE_TEST_DATABASE_URL is required for PostgreSQL restore tests')
    if not shutil.which('pg_restore'): sys.exit('pg_restore is required')
    subprocess.run(['pg_restore','--clean','--if-exists','--no-owner','--dbname',target,str(b)],check=True)
    print('PASS PostgreSQL pg_restore completed')
else: sys.exit('Unknown backup type')
