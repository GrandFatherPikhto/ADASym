"""
Главный исполняемый модуль.

Запускать из папки adasim/ (например, `python main.py`) — как и раньше, только
теперь код разложен по core/ltspice_io/report вместо одной плоской папки.

Загружает конфигурацию (YAML), выполняет расчёт номиналов, читает .asc через
asc_parser (с именами пинов из .asy — см. asy_parser.py), запускает LTspice,
строит и сохраняет графики, генерирует итоговый отчёт.
"""

from pathlib import Path

from logger_config import logger, setup_logging
from config import load_config
from core.calculation import select_components
from ltspice_io.runner import LTspiceRunner
from ltspice_io.asc_parser import parse_asc
from ltspice_io.readable_report import generate_readable_report
from report.plotting import plot_time_domain, plot_spectrum, plot_degradation, plot_input_currents
from report.text_report import generate_report


def select_best_combination(params: dict) -> dict:
    """Выбирает лучшую комбинацию номиналов из рассчитанных."""
    combinations = select_components(params)
    chosen = combinations[0].copy()
    chosen['R_load'] = params['R_load']
    chosen['R_TIA'] = params['R_TIA']
    logger.info(f"Выбрана комбинация: Ra={chosen['Ra']} Ом, Rf={chosen['Rf_e96']} Ом, "
                f"Rb={chosen['Rb_e96']} Ом, Cf={chosen['Cf']} пФ, R_TIA={chosen['R_TIA']} Ом")
    return chosen


def build_readable_schematic_report(config: dict) -> Path | None:
    """Строит читаемый отчёт по .asc напрямую (без промежуточного .net от LTspice)."""
    sch_cfg = config.get('schematic', {})
    nl_cfg = config.get('netlist_generator', {})
    if not nl_cfg.get('generate_netlist', False):
        return None

    asc_path = sch_cfg['path']
    search_paths = sch_cfg.get('symbol_search_paths', ['.'])
    schematic = parse_asc(asc_path, search_paths)

    output_dir = Path(nl_cfg.get('output_dir', 'net'))
    readable_path = output_dir / f"{Path(asc_path).stem}_readable.txt"
    generate_readable_report(schematic, Path(asc_path).name, readable_path)
    logger.info(f"Читаемый отчёт по схеме (с именами пинов): {readable_path}")
    return readable_path


def setup_runner(config: dict) -> LTspiceRunner:
    return LTspiceRunner(
        schematic_path=config['schematic']['path'],
        ltspice_exe=config['ltspice']['executable'],
        temp_dir=config['simulation']['temp_dir'],
        output_dir=config['simulation']['output_dir']
    )


def run_single_simulation(runner: LTspiceRunner, chosen: dict, freq: float) -> tuple:
    raw_path, log_path = runner.run(chosen, freq)
    csv_path = runner.export_raw_to_csv(raw_path)
    thd = runner.get_thd(log_path)
    harmonics, amplitudes = runner.get_fourier_data(log_path)
    return raw_path, log_path, csv_path, thd, harmonics, amplitudes


def generate_plots(plots_cfg: dict, output_dir: str, csv_path: str, harmonics: list, amplitudes: list,
                    thd: str, frequencies: list, thd_results: list = None, r_tia: float = None):
    save = plots_cfg.get('save', True)
    show = plots_cfg.get('show', False)

    if plots_cfg.get('time_domain', False):
        plot_time_domain(csv_path, output_dir, save=save, show=show)
    if plots_cfg.get('spectrum', False):
        plot_spectrum(harmonics, amplitudes, thd, output_dir, save=save, show=show)
    if plots_cfg.get('input_currents', False) and r_tia is not None:
        plot_input_currents(csv_path, r_tia, output_dir, save=save, show=show)
    if plots_cfg.get('degradation', False) and thd_results is not None:
        plot_degradation(frequencies, thd_results, output_dir, save=save, show=show)


def main():
    setup_logging("simulation.log")
    config = load_config("config.yaml")

    # 1. Читаемый отчёт по схеме (имена пинов, не номера)
    readable_net_path = build_readable_schematic_report(config)

    # 2. Подбор номиналов
    chosen = select_best_combination(config['params'])
    chosen.update(config.get('tran_settings', {}))

    # 3. Раннер
    runner = setup_runner(config)
    r_tia = chosen['R_TIA']

    # 4. Одиночная симуляция на первой частоте
    first_freq = config['frequencies'][0]
    raw_path, log_path, csv_path, thd, harmonics, amplitudes = run_single_simulation(
        runner, chosen, first_freq
    )

    # 5. Графики (сохраняются в output_dir, по умолчанию без блокирующего show())
    plots_cfg = config.get('plots', {})
    generate_plots(plots_cfg, config['simulation']['output_dir'], csv_path,
                    harmonics, amplitudes, thd, None, None, r_tia)

    # 6. Свип по частотам для деградации (если запрошено)
    thd_results = None
    if plots_cfg.get('degradation', False):
        logger.info("Запуск sweep по частотам для оценки деградации THD...")
        thd_results = runner.degradation_sweep(chosen, config['frequencies'])
        plot_degradation(config['frequencies'], thd_results, config['simulation']['output_dir'],
                          save=plots_cfg.get('save', True), show=plots_cfg.get('show', False))

    # 7. Отчёт
    sim_info = {
        'freq': first_freq,
        'thd': thd,
        'csv_path': csv_path,
        'log_path': log_path,
        'readable_net_path': readable_net_path,
    }
    generate_report(config, chosen, sim_info, config['simulation']['output_dir'])

    logger.info("=== Процесс завершён успешно ===")


if __name__ == "__main__":
    main()
