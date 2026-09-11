from app.db import normalize_database_url


def test_hosted_postgres_urls_use_the_bundled_psycopg_driver():
    assert normalize_database_url('postgresql://u:p@host:5432/db') == 'postgresql+psycopg://u:p@host:5432/db'
    assert normalize_database_url('postgres://u:p@host:5432/db') == 'postgresql+psycopg://u:p@host:5432/db'
    assert normalize_database_url('postgresql+psycopg://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert normalize_database_url('sqlite:///./data/pursuitnova.db') == 'sqlite:///./data/pursuitnova.db'
