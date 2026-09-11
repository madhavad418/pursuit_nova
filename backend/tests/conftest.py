import os, tempfile
DB=os.path.join(tempfile.gettempdir(),'pursuitnova_51_pytest.db')
try: os.remove(DB)
except FileNotFoundError: pass
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
os.environ['SEED_DEMO']='true'
os.environ['SEED_DEMO_DATA']='true'
os.environ['JWT_SECRET']='test-secret-key-that-is-long-enough-for-hs256-validation-2026'
os.environ['COOKIE_SECURE']='false'

import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope='session')
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def login():
    def _login(client,email='bd.exec1@jsan.local',password='PursuitNovaDemo@2026',otp=None):
        r=client.post('/api/auth/login',json={'email':email,'password':password,'otp':otp})
        assert r.status_code==200, r.text
        return r.json()
    return _login

@pytest.fixture
def csrf_headers():
    def _h(client):
        token=client.cookies.get('pursuitnova_csrf')
        return {'X-CSRF-Token':token} if token else {}
    return _h
