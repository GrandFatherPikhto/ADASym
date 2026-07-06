"""
Модуль построения графиков на основе данных симуляции.

Отличие от старой версии: каждая функция теперь принимает output_dir и флаги
save/show, вместо безусловного plt.show(). По умолчанию сохраняем и не
показываем — удобно для автоматических прогонов (degradation sweep и т.п.),
где plt.show() блокировал бы выполнение на каждой частоте.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from logger_config import logger


def _finish(fig, output_dir: str | Path | None, filename: str, save: bool, show: bool):
    if save:
        if output_dir is None:
            raise ValueError("output_dir обязателен, если save=True")
        out_path = Path(output_dir) / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        logger.info(f"График сохранён: {out_path}")
    if show:
        plt.show()
    plt.close(fig)


def plot_time_domain(csv_path: str, output_dir: str | Path | None = None,
                      save: bool = True, show: bool = False, filename: str = "time_domain.png"):
    logger.info(f"Построение временных графиков из {csv_path}")
    df = pd.read_csv(csv_path)

    if 'V(signal)' not in df.columns or 'I(Rload)' not in df.columns:
        logger.error("В CSV отсутствуют столбцы 'V(signal)' или 'I(Rload)'")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    time_us = df['Time'] * 1e6

    ax1.plot(time_us, df['V(signal)'], color='blue', label='Выходное напряжение')
    ax1.set_ylabel('Напряжение (В)')
    ax1.set_title('Результаты симуляции ADA4870')
    ax1.grid(True, linestyle='--')
    ax1.legend()

    ax2.plot(time_us, df['I(Rload)'], color='red', label='Ток нагрузки')
    ax2.set_ylabel('Ток (А)')
    ax2.set_xlabel('Время (мкс)')
    ax2.grid(True, linestyle='--')
    ax2.legend()

    plt.tight_layout()
    _finish(fig, output_dir, filename, save, show)


def plot_spectrum(harmonics: list[int], amplitudes: list[float], thd_text: str = "",
                   output_dir: str | Path | None = None,
                   save: bool = True, show: bool = False, filename: str = "spectrum.png"):
    if not harmonics:
        logger.warning("Нет данных гармоник для построения спектра")
        return

    logger.info("Построение спектра гармоник")
    fig = plt.figure(figsize=(10, 6))
    plt.bar(harmonics, amplitudes, color='purple', alpha=0.7)
    plt.yscale('log')
    plt.title(f'Спектр выходного сигнала\nTHD = {thd_text}')
    plt.xlabel('Номер гармоники')
    plt.ylabel('Амплитуда (В)')
    plt.xticks(harmonics)
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    _finish(fig, output_dir, filename, save, show)


def plot_degradation(frequencies: list[float], thd_list: list[float],
                      output_dir: str | Path | None = None,
                      save: bool = True, show: bool = False, filename: str = "degradation.png"):
    logger.info("Построение графика деградации THD")
    fig = plt.figure(figsize=(10, 5))
    plt.semilogx(frequencies, thd_list, 'o-r', linewidth=2)
    plt.title('Деградация THD от частоты')
    plt.xlabel('Частота (Гц)')
    plt.ylabel('THD (%)')
    plt.grid(True, which='both', linestyle='--')
    _finish(fig, output_dir, filename, save, show)


def plot_input_currents(csv_path: str, r_tia: float,
                         output_dir: str | Path | None = None,
                         save: bool = True, show: bool = False, filename: str = "input_currents.png"):
    logger.info(f"Построение графиков токов из {csv_path}, R_TIA={r_tia} Ом")
    df = pd.read_csv(csv_path)

    required = ['V(inn)', 'V(n001)', 'V(inp)', 'V(n002)']
    if not all(col in df.columns for col in required):
        logger.warning("В CSV нет нужных колонок для вычисления токов. Пропускаем.")
        return

    iouta = (df['V(n001)'] - df['V(inn)']) / r_tia
    ioutb = (df['V(n002)'] - df['V(inp)']) / r_tia
    time_us = df['Time'] * 1e6

    fig = plt.figure(figsize=(10, 5))
    plt.plot(time_us, iouta, label='IOUTA', color='blue')
    plt.plot(time_us, ioutb, label='IOUTB', color='red', linestyle='--')
    plt.xlabel('Время (мкс)')
    plt.ylabel('Ток (А)')
    plt.title('Входные токи IOUTA и IOUTB (расчёт по напряжениям)')
    plt.grid(True)
    plt.legend()
    _finish(fig, output_dir, filename, save, show)
