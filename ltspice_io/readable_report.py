"""
Генерация читаемого отчёта по схеме — теперь с ИМЕНАМИ пинов (IN+/IN-/OUT/V+/V-/SD),
а не голыми номерами SpiceOrder, как было в старой версии на сыром .net.

Строится напрямую из AscSchematic (см. asc_parser.py), то есть из самого .asc,
без промежуточного запуска `LTspice -netlist` — это не только проще, но и точнее:
сырой .net сворачивает имена пинов в номера, и именно это отняло больше всего
времени при ручной сверке платы (см. историю ревью Ra/Rb/Rf).
"""

from __future__ import annotations

from pathlib import Path

from .asc_parser import AscSchematic


def generate_readable_report(schematic: AscSchematic, schematic_name: str, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    components = schematic.all_components()

    lines = [
        f"=== ЧИТАЕМЫЙ ОТЧЁТ ПО СХЕМЕ: {schematic_name} ===",
        f"Всего компонентов: {len(components)}",
        "-" * 80,
        f"{'Имя':<10} | {'Символ':<20} | {'Номинал':<15} | Пины -> Цепи",
        "-" * 80,
    ]

    for comp in sorted(components, key=lambda c: c.ref):
        pins_str = ", ".join(
            f"{pin_name}->{schematic.net_of(comp.ref, pin_name)}"
            for pin_name in comp.pins
        )
        value = comp.value or ""
        lines.append(f"{comp.ref:<10} | {comp.symbol_ref:<20} | {value:<15} | {pins_str}")

    lines.append("")
    lines.append("=" * 80)
    lines.append("--- АНАЛИЗ ЦЕПЕЙ (какие пины какого компонента объединяет каждая цепь) ---")

    net_to_pins: dict[str, list[str]] = {}
    for ref, pin_name, net_name in schematic.pin_table():
        net_to_pins.setdefault(net_name, []).append(f"{ref}.{pin_name}")

    for net_name in sorted(net_to_pins):
        members = ", ".join(net_to_pins[net_name])
        lines.append(f"Цепь [{net_name:<10}] -> {members}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
