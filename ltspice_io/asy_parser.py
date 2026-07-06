"""
Парсер файлов символов LTspice (.asy).

Извлекает для каждого пина: локальные координаты (x, y), номер в SPICE-порядке
(SpiceOrder) и "человеческое" имя (PinName), если оно задано.

ВАЖНО: .asy-файлы LTspice обычно в кодировке UTF-16LE (с CRLF), а не UTF-8/CP1251,
как остальные текстовые файлы проекта — это то, на чём я сам спотыкался при ручном
разборе. Поэтому чтение всегда пробует UTF-16LE в первую очередь.

Не хардкодим офсеты пинов ни для каких символов, включая "стандартные" (res, cap,
voltage, bi) — это единственный надёжный способ не наврать себе, как уже
случилось один раз с Ra/Rb на реальной плате. Если для проекта нужны и
примитивы LTspice — просто добавь путь к LTspice/lib/sym в symbol_search_paths
при создании AscParser (см. asc_parser.py), и они прочитаются тем же кодом.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolPin:
    """Один пин символа в ЛОКАЛЬНЫХ координатах (до поворота/переноса)."""
    spice_order: int
    name: str
    x: int
    y: int


def _read_asy_text(path: Path) -> str:
    """
    Читает .asy, определяя кодировку по содержимому, а не перебором с расчётом
    на исключение. Это важно: UTF-16LE почти никогда не кидает UnicodeDecodeError
    даже на обычном ASCII/UTF-8 файле (просто превращает его в мусорные
    иероглифы) — поэтому порядок "пробуем декодировать, ловим исключение" для
    UTF-16 в принципе не работает как детектор. Вместо этого:
      1. Проверяем BOM (FF FE / FE FF) — однозначный признак UTF-16.
      2. Если BOM нет — считаем долю нулевых байт. У настоящего UTF-16LE текста
         из ASCII-символов примерно каждый второй байт — 0x00; у обычного
         UTF-8/ASCII файла нулевых байт почти нет.
      3. Иначе — обычный UTF-8 (с фолбэком на cp1251).
    """
    raw = path.read_bytes()
    if not raw:
        return ""

    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be")

    # Без BOM: доля нулевых байт — надёжный признак UTF-16LE/BE без BOM
    # (кастомные .asy, сохранённые LTspice, часто именно такие).
    sample = raw[:2000]
    zero_ratio = sample.count(0) / len(sample)
    if zero_ratio > 0.3:
        # Чётные позиции нулевые -> LE, нечётные -> BE
        even_zeros = sum(1 for i in range(0, len(sample), 2) if sample[i:i+1] == b"\x00")
        odd_zeros = sum(1 for i in range(1, len(sample), 2) if sample[i:i+1] == b"\x00")
        try:
            return raw.decode("utf-16-le" if odd_zeros >= even_zeros else "utf-16-be")
        except UnicodeDecodeError:
            pass

    for enc in ("utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_asy(path: str | Path) -> dict[int, SymbolPin]:
    """
    Разбирает .asy и возвращает {spice_order: SymbolPin}.

    Формат в файле (см. пример ADA4870.asy/ADA4807-2.asy):
        PIN -32 16 NONE 8
        PINATTR PinName 100
        PINATTR SpiceOrder 1
    Блок PIN описывает координаты, последующие PINATTR — атрибуты этого же пина,
    вплоть до следующего PIN или конца файла.
    """
    path = Path(path)
    text = _read_asy_text(path)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    pins: dict[int, SymbolPin] = {}

    pin_re = re.compile(r"^PIN\s+(-?\d+)\s+(-?\d+)\s+\S+\s+\d+")
    current_xy: tuple[int, int] | None = None
    current_name: str | None = None
    current_order: int | None = None
    fallback_counter = 0  # используется, когда явного SpiceOrder нет (напр. штатные res/bi)

    def flush():
        nonlocal fallback_counter
        if current_xy is None:
            return
        # Если SpiceOrder не задан явно (нет PINATTR SpiceOrder у этого PIN) —
        # не роняем пин молча, а нумеруем по порядку появления в файле.
        order = current_order
        if order is None:
            fallback_counter += 1
            order = fallback_counter
        name = current_name if current_name is not None else str(order)
        pins[order] = SymbolPin(
            spice_order=order, name=name,
            x=current_xy[0], y=current_xy[1],
        )

    for line in lines:
        m = pin_re.match(line)
        if m:
            flush()
            current_xy = (int(m.group(1)), int(m.group(2)))
            current_name = None
            current_order = None
            continue
        if line.startswith("PINATTR PinName"):
            current_name = line.split(None, 2)[2]
        elif line.startswith("PINATTR SpiceOrder"):
            current_order = int(line.split(None, 2)[2])

    flush()
    return pins


def find_asy(symbol_ref: str, search_paths: list[Path]) -> Path | None:
    """
    Ищет файл символа по ссылке из SYMBOL-строки .asc (например, 'OpAmps\\ADA4870'
    или просто 'res') в списке директорий. LTspice сам использует '\\' как
    разделитель подпапки библиотеки даже на не-Windows путях, поэтому нормализуем.
    """
    rel = symbol_ref.replace("\\\\", "/").replace("\\", "/")
    for base in search_paths:
        candidate = Path(base) / f"{rel}.asy"
        if candidate.exists():
            return candidate
    return None
