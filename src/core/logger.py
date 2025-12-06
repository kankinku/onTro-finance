import logging
import sys
from src.core.config import settings

def setup_logger(name: str = "ontofin"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if settings.ENV == "dev" else logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()
# Usage: from src.core.logger import logger
