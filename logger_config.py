"""
Модуль настройки логирования.
Все части проекта импортируют настроенный логгер 'ADASim'.
Уровень по умолчанию INFO, в файл пишется DEBUG.

(Без изменений от исходной версии — Фаза 1 намеренно эту логику не трогает.)
"""

import logging
import sys


def setup_logging(log_file: str = "simulation.log") -> logging.Logger:
    logger = logging.getLogger('ADASim')
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s.%(module)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = logging.getLogger('ADASim')
