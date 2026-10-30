"""Application configuration and local paths."""

import logging
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"
DATABASE_PATH = Path(os.environ.get("ATTENDANCE_DB_PATH", DATA_DIR / "attendance.db"))
ATTENDANCE_REVIEW_THRESHOLD = 75.0
AUDIO_ACTIVITY_LOW_THRESHOLD = 10.0
AUDIO_ACTIVITY_HIGH_THRESHOLD = 90.0
VIDEO_SAMPLE_INTERVAL_SECONDS = 1.0
AUDIO_RMS_THRESHOLD = 0.02
MAX_UPLOAD_SIZE_MB = 100

DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=REPORTS_DIR / "app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

