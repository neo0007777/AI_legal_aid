#!/usr/bin/env python3
"""
Standalone Compliance Refresh Worker for Render Cron Jobs.
Runs as a periodic job (e.g. every 12 hours) decoupled from the FastAPI web server.
"""
import sys
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("LexSetu.ComplianceWorker")

def run():
    logger.info("Starting scheduled compliance alerts refresh...")
    from models.database import SessionLocal
    from services.compliance_fetcher import refresh_compliance_alerts

    db = SessionLocal()
    try:
        results = refresh_compliance_alerts(db)
        logger.info(f"Compliance refresh succeeded. Processed: {results}")
    except Exception as e:
        logger.error(f"Compliance refresh job failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()
    logger.info("Compliance worker finished successfully.")

if __name__ == "__main__":
    run()
