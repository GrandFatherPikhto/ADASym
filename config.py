"""
Загрузка конфигурации из YAML (было — JSON).

Требует pyyaml>=5.1 (в старых версиях экспоненциальная запись без десятичной
точки в мантиссе, например 27e-12, парсится как строка, а не float — если
используешь версию pyyaml < 5.1, пиши 27.0e-12).
"""

import sys
import yaml
from logger_config import logger


def load_config(config_path: str) -> dict:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Конфигурация загружена из {config_path}")
        return config
    except Exception as e:
        logger.critical(f"Не удалось загрузить конфиг: {e}")
        sys.exit(1)
