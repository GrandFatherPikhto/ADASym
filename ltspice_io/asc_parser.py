"""
Парсер схемы LTspice (.asc): WIRE, FLAG, SYMBOL -> граф электрических цепей.

В отличие от предыдущей версии (netlist_generator.py, работавшей с текстовым
.net от `LTspice -netlist`), этот модуль читает САМ .asc и использует реальные
координаты пинов из .asy (через asy_parser), а не пытается угадать их или
трассировать провода на глаз. Именно так мы и сверяли Ra/Rb/Rf вручную —
здесь это автоматизировано.

Поддерживаются повороты/зеркалирования R0/R90/R180/R270/M0/M90/M180/M270.
Матрицы поворота — стандартная договорённость LTspice; R0-случай проверен
вручную на реальном проекте (ADA4870/ADA4807-2, см. историю ревью), остальные
повороты не помешает перепроверить на любом символе с известной, "человеческой"
разводкой (например, res), если возникнут сомнения.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .asy_parser import parse_asy, find_asy, SymbolPin

Point = tuple[int, int]

_ROTATIONS = {
    "R0":   lambda x, y: (x, y),
    "R90":  lambda x, y: (-y, x),
    "R180": lambda x, y: (-x, -y),
    "R270": lambda x, y: (y, -x),
    "M0":   lambda x, y: (-x, y),
    "M90":  lambda x, y: (y, x),
    "M180": lambda x, y: (x, -y),
    "M270": lambda x, y: (-y, -x),
}


@dataclass
class Component:
    ref: str                 # InstName, например "Ra" или "U1"
    symbol_ref: str           # то, что после SYMBOL, например "OpAmps\\ADA4870" или "res"
    x: int
    y: int
    rotation: str
    value: str | None = None
    pins: dict[str, Point] = field(default_factory=dict)   # pin_name -> абсолютные координаты


class _UnionFind:
    def __init__(self):
        self.parent: dict[Point, Point] = {}

    def find(self, p: Point) -> Point:
        self.parent.setdefault(p, p)
        while self.parent[p] != p:
            self.parent[p] = self.parent[self.parent[p]]
            p = self.parent[p]
        return p

    def union(self, a: Point, b: Point):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


class AscSchematic:
    """Разобранная схема: компоненты с абсолютными координатами пинов + сеть цепей."""

    def __init__(self, components: list[Component], nets: dict[Point, str], uf: _UnionFind):
        self._components = {c.ref: c for c in components}
        self._nets = nets          # представитель union-find -> имя цепи (если есть FLAG)
        self._uf = uf

    def net_of(self, ref: str, pin_name: str) -> str:
        """Возвращает имя цепи (или синтетическое 'N_x_y', если явного имени нет)."""
        comp = self._components[ref]
        point = comp.pins[pin_name]
        root = self._uf.find(point)
        if root in self._nets:
            return self._nets[root]
        return f"N_{root[0]}_{root[1]}"

    def component(self, ref: str) -> Component:
        return self._components[ref]

    def all_components(self) -> list[Component]:
        return list(self._components.values())

    def pin_table(self) -> list[tuple[str, str, str]]:
        """Плоский список (component_ref, pin_name, net_name) для читаемого отчёта."""
        rows = []
        for ref, comp in self._components.items():
            for pin_name in comp.pins:
                rows.append((ref, pin_name, self.net_of(ref, pin_name)))
        return sorted(rows)


def parse_asc(asc_path: str | Path, symbol_search_paths: list[str | Path]) -> AscSchematic:
    """
    Читает .asc и строит AscSchematic.

    symbol_search_paths: директории, где искать .asy — как минимум папка самого
    проекта (для кастомных символов типа OpAmps\\ADA4870), и по-хорошему ещё
    LTspice/lib/sym, если нужны стандартные примитивы (res, cap, voltage, bi...).
    """
    asc_path = Path(asc_path)
    search_paths = [Path(p) for p in symbol_search_paths]
    text = asc_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    uf = _UnionFind()
    named_nets: dict[Point, str] = {}
    pending_symbols: list[tuple[str, int, int, str]] = []  # (symbol_ref, x, y, rotation)
    components: list[Component] = []

    wire_re = re.compile(r"^WIRE\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)")
    flag_re = re.compile(r"^FLAG\s+(-?\d+)\s+(-?\d+)\s+(\S+)")
    symbol_re = re.compile(r"^SYMBOL\s+(\S+)\s+(-?\d+)\s+(-?\d+)\s+(R0|R90|R180|R270|M0|M90|M180|M270)")
    instname_re = re.compile(r"^SYMATTR\s+InstName\s+(\S+)")
    value_re = re.compile(r"^SYMATTR\s+Value\s+(.+)$")

    current_symbol: tuple[str, int, int, str] | None = None
    current_instname: str | None = None
    current_value: str | None = None

    def flush_symbol():
        if current_symbol is not None and current_instname is not None:
            pending_symbols.append((current_symbol[0], current_symbol[1],
                                     current_symbol[2], current_symbol[3],
                                     current_instname, current_value))

    for raw_line in lines:
        line = raw_line.strip()

        m = wire_re.match(line)
        if m:
            x1, y1, x2, y2 = map(int, m.groups())
            uf.union((x1, y1), (x2, y2))
            continue

        m = flag_re.match(line)
        if m:
            x, y, name = int(m.group(1)), int(m.group(2)), m.group(3)
            if name != "0":  # "0" это GND, но пусть тоже станет читаемым именем
                named_nets[(x, y)] = name
            else:
                named_nets[(x, y)] = "0"
            continue

        m = symbol_re.match(line)
        if m:
            flush_symbol()
            current_symbol = (m.group(1), int(m.group(2)), int(m.group(3)), m.group(4))
            current_instname = None
            current_value = None
            continue

        m = instname_re.match(line)
        if m:
            current_instname = m.group(1)
            continue

        m = value_re.match(line)
        if m and current_value is None:
            current_value = m.group(1)
            continue

    flush_symbol()

    # Раскрываем каждый найденный символ через его .asy
    asy_cache: dict[str, dict[int, SymbolPin]] = {}
    for symbol_ref, sx, sy, rotation, instname, value in pending_symbols:
        if symbol_ref not in asy_cache:
            asy_path = find_asy(symbol_ref, search_paths)
            if asy_path is None:
                raise FileNotFoundError(
                    f"Не найден .asy для символа '{symbol_ref}' "
                    f"(искал в {[str(p) for p in search_paths]}). "
                    f"Добавь директорию с этим символом в symbol_search_paths."
                )
            asy_cache[symbol_ref] = parse_asy(asy_path)

        transform = _ROTATIONS[rotation]
        comp = Component(ref=instname, symbol_ref=symbol_ref, x=sx, y=sy,
                          rotation=rotation, value=value)
        for pin in asy_cache[symbol_ref].values():
            lx, ly = transform(pin.x, pin.y)
            abs_point = (sx + lx, sy + ly)
            comp.pins[pin.name] = abs_point
            uf.union(abs_point, abs_point)  # гарантируем, что точка есть в union-find

        components.append(comp)

    # Проставляем имена цепей на корни union-find
    nets: dict[Point, str] = {}
    for point, name in named_nets.items():
        root = uf.find(point)
        nets[root] = name

    return AscSchematic(components, nets, uf)
