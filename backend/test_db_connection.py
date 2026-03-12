"""Test Supabase connection."""
import logging

from database.db_writer import DatabaseWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_connection() -> bool:
    db = DatabaseWriter()
    ok = db.check_connection()
    if ok:
        logger.info('Supabase connection successful')
        logger.info('Connected to: %s', db.supabase_url)
    else:
        logger.error('Supabase connection failed')
    return ok


if __name__ == '__main__':
    test_connection()
