"""
Главный исполняемый модуль.

Загружает конфигурацию, выполняет расчёт номиналов, запускает LTspice,
строит графики и генерирует итоговый отчёт.
"""

import os
import json
import sys
from pathlib import Path

from logger_config import logger, setup_logging
from calculation import select_components
from simulation import LTspiceRunner
from plotting import plot_time_domain, plot_spectrum, plot_degradation
from report import generate_report


def main():
    # 1. Настройка логирования (файл simulation.log)
    setup_logging("simulation.log")
    print(os.getcwd())

    # 2. Загрузка конфигурации из JSON
    config_path = "config.json"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"Конфигурация загружена из {config_path}")
    except Exception as e:
        logger.critical(f"Не удалось загрузить конфиг: {e}")
        sys.exit(1)

    # 3. Расчёт номиналов
    try:
        combinations = select_components(config['params'])
    except ValueError as e:
        logger.critical(e)
        sys.exit(1)

    # Берём первую (лучшую) комбинацию
    chosen = combinations[0]
    chosen['R_load'] = config['params']['R_load']   # <-- добавляем нагрузку
    chosen.update(config.get('tran_settings', {}))  # добавляем настройки времени    
    logger.info(f"Выбрана комбинация: Ra={chosen['Ra']} Ом, Rf={chosen['Rf_e96']} Ом, "
                f"Rb={chosen['Rb_e96']} Ом, Cf={chosen['Cf']} пФ, R_load={chosen['R_load']} Ом")

    # 4. Инициализация раннера LTspice
    runner = LTspiceRunner(
        schematic_path=config['schematic']['path'],
        ltspice_exe=config['ltspice']['executable'],
        temp_dir=config['simulation']['temp_dir'],
        output_dir=config['simulation']['output_dir']
    )

    # 5. Запуск симуляции (частота берётся из первого элемента списка или фиксированная)
    freq = 1.7e6  # можно брать из конфига или аргументов командной строки
    try:
        raw_path, log_path = runner.run(chosen, freq)
    except Exception as e:
        logger.critical(f"Ошибка симуляции: {e}")
        sys.exit(1)

    # 6. Экспорт CSV
    csv_path = runner.export_raw_to_csv(raw_path)

    # 7. Построение графиков
    plot_time_domain(str(csv_path))

    harmonics, amplitudes = runner.get_fourier_data(log_path)
    thd = runner.get_thd(log_path)
    plot_spectrum(harmonics, amplitudes, thd)

    # 8. Генерация отчёта
    sim_info = {
        'freq': freq,
        'thd': thd,
        'csv_path': str(csv_path),
        'log_path': log_path
    }
    generate_report(config, chosen, sim_info, config['simulation']['output_dir'])

    logger.info("=== Процесс завершён успешно ===")

    # Пример после расчёта и одиночной симуляции
    freqs = config['frequencies']   # список из JSON
    chosen = combinations[0]
    chosen['R_load'] = config['params']['R_load']

    runner = LTspiceRunner(
        schematic_path=config['schematic']['path'],
        ltspice_exe=config['ltspice']['executable'],
        temp_dir=config['simulation']['temp_dir'],
        output_dir=config['simulation']['output_dir']
        )

    thd_results = runner.degradation_sweep(chosen, freqs)
    plot_degradation(freqs, thd_results)    


if __name__ == "__main__":
    main()