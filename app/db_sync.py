import psycopg2

from app.config import get_settings


def get_sync_conn():
    return psycopg2.connect(get_settings().database_url)
