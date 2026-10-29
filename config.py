"""
Centralized Configuration for Hardware Inventory Dashboard.
Includes directory paths, health evaluation thresholds, and logging setups.
"""
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import os

# Base directory of the application
BASE_DIR = Path(__file__).resolve().parent

# Storage Directories
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
NORMALIZED_DIR = DATA_DIR / "normalized"
CHANGES_DIR = DATA_DIR / "changes"
UPLOADS_DIR = BASE_DIR / "uploads"
LOGS_DIR = BASE_DIR / "logs"

# Ensure all essential directories exist
for directory in [DATA_DIR, RAW_DIR, SNAPSHOTS_DIR, NORMALIZED_DIR, CHANGES_DIR, UPLOADS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Application Settings
SECRET_KEY = os.environ.get("SECRET_KEY", "hardware-inventory-secret-key-2026")
MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB max upload
ALLOWED_EXTENSIONS = {"txt"}

# Hardware Health & Alert Thresholds
LOW_STORAGE_WARNING_PERCENT = 15.0   # Free space < 15% triggers Warning
LOW_STORAGE_CRITICAL_PERCENT = 5.0   # Free space < 5% triggers Critical
RECOMMENDED_MIN_RAM_GB = 16.0        # < 16 GB triggers RAM upgrade recommendation
RECOMMENDED_MIN_CPU_CORES = 4        # < 4 cores triggers CPU upgrade recommendation

# Prometheus Monitoring Configuration (Pipeline B)
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://172.16.10.38:9090").rstrip("/")
PROMETHEUS_TIMEOUT = int(os.environ.get("PROMETHEUS_TIMEOUT", "5"))
MONITORING_CACHE_TTL_SECONDS = int(os.environ.get("MONITORING_CACHE_TTL_SECONDS", "10"))

# Live Monitoring Health Thresholds
CPU_WARNING_PERCENT = float(os.environ.get("CPU_WARNING_PERCENT", "80.0"))
CPU_CRITICAL_PERCENT = float(os.environ.get("CPU_CRITICAL_PERCENT", "95.0"))
MEMORY_WARNING_PERCENT = float(os.environ.get("MEMORY_WARNING_PERCENT", "85.0"))
MEMORY_CRITICAL_PERCENT = float(os.environ.get("MEMORY_CRITICAL_PERCENT", "95.0"))
DISK_WARNING_PERCENT = float(os.environ.get("DISK_WARNING_PERCENT", "85.0"))
DISK_CRITICAL_PERCENT = float(os.environ.get("DISK_CRITICAL_PERCENT", "95.0"))

# Configurable Service & Process Monitoring Lists
MONITORED_SERVICES = [
    s.strip() for s in os.environ.get("MONITORED_SERVICES", "Spooler,LanmanServer,wuauserv,EventLog").split(",") if s.strip()
]
MONITORED_PROCESSES = [
    p.strip() for p in os.environ.get("MONITORED_PROCESSES", "chrome.exe,sqlservr.exe,postgres.exe").split(",") if p.strip()
]

# NVIDIA NIM / OpenAI Configuration for AI Insights
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_API_KEY = os.environ.get(
    "NVIDIA_API_KEY",
    "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"
)
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "mistralai/mistral-nemotron")
AI_INSIGHTS_CACHE_TTL_SECONDS = int(os.environ.get("AI_INSIGHTS_CACHE_TTL_SECONDS", "3600"))

# Predictive Analysis Risk Engine Configuration
RISK_THRESHOLD_CRITICAL = 75
RISK_THRESHOLD_HIGH = 50
RISK_THRESHOLD_MODERATE = 25

# Setup Centralized Loggers
def setup_logger(name: str, log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Configures and returns a named logger writing to a rotating log file."""
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)

    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)
        # Also log to console for development convenience
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger

app_logger = setup_logger("application", LOGS_DIR / "application.log")
parser_logger = setup_logger("parser", LOGS_DIR / "parser.log")
change_logger = setup_logger("change_detector", LOGS_DIR / "change_detector.log")
monitoring_logger = setup_logger("monitoring", LOGS_DIR / "monitoring.log")
predictive_logger = setup_logger("predictive", LOGS_DIR / "predictive.log")
ai_logger = setup_logger("ai_insights", LOGS_DIR / "ai_insights.log")
error_logger = setup_logger("error", LOGS_DIR / "error.log", level=logging.WARNING)
