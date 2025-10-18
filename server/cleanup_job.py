"""
Retention cleanup job for periodic database maintenance.
Run this script periodically (e.g., via cron or scheduled task) to clean up old data.
"""
import sys
import logging
from models import SessionLocal
from db_utils import run_all_retention_cleanups

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Execute all retention cleanup jobs."""
    logger.info("Starting retention cleanup job")
    
    db = SessionLocal()
    try:
        results = run_all_retention_cleanups(db)
        logger.info(f"Cleanup completed successfully: {results}")
        return 0
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
