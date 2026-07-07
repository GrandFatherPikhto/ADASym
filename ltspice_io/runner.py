"""
Модуль запуска симуляции LTspice и обработки выходных файлов.

Содержит класс LTspiceRunner, который инкапсулирует:
- создание временной папки и очистку,
- редактирование схемы через PyLTSpice,
- запуск и ожидание завершения,
- экспорт результатов в CSV,
- извлечение THD и данных Фурье из лога.

(Перенесено из simulation.py без изменения логики — только путь модуля.)
"""

import re
from pathlib import Path
import pandas as pd
from PyLTSpice import SimRunner, SpiceEditor, RawRead
from logger_config import logger


class LTspiceRunner:
    def __init__(self, schematic_path: str, ltspice_exe: str,
                 temp_dir: str = "./temp", output_dir: str = "./out"):
        self.schematic_path = schematic_path
        self.ltspice_exe = ltspice_exe
        self.temp_dir = Path(temp_dir)
        self.output_dir = Path(output_dir)
        self.raw_file = None
        self.log_file = None

        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _clean_temp(self):
        """Удаляет старые .raw и .log файлы из временной папки, чтобы не путать запуски."""
        for f in self.temp_dir.glob("*"):
            if f.suffix in (".raw", ".log"):
                try:
                    f.unlink()
                    logger.debug(f"Удалён старый файл: {f}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить {f}: {e}")

    def run(self, params: dict, freq_hz: float) -> tuple[str, str]:
        logger.info("=== Подготовка симуляции ===")
        self._clean_temp()

        editor = SpiceEditor(self.schematic_path)

        periods_transient = params.get('periods_transient', 10)
        periods_analysis = params.get('periods_analysis', 10)
        points_per_period = params.get('points_per_period', 1000)

        T = 1.0 / freq_hz if freq_hz > 0 else 1e-6
        tran_end = (periods_transient + periods_analysis) * T
        tran_start = periods_transient * T
        time_step = T / points_per_period

        # editor.add_instruction(f" .MEAS TRAN Vfinal FIND V(SIGNAL) AT={tran_end - time_step:.6e}")
        editor.add_instruction(
            f" .tran 0 {tran_end:.6e} {tran_start:.6e} {time_step:.6e}"
        )
        editor.add_instruction(f" .four {freq_hz} 10 5 V(SIGNAL)")
        editor.add_instruction(" .options plotwinsize=0")
        editor.add_instruction(" .options numdgt=7")

        editor.set_parameter('FREQ', str(freq_hz))
        editor.set_parameter('RfVal', str(params['Rf_e96']))
        editor.set_parameter('RloadVal', str(params['R_load']))

        editor.set_component_value('Rfn', str(params['R_TIA']))
        editor.set_component_value('Rfp', str(params['R_TIA']))
        editor.set_component_value('Cf', f"{params['Cf']}p")
        editor.set_component_value('Ra', str(params['Ra']))
        editor.set_component_value('Rb', str(params['Rb_e96']))
        editor.set_component_value('Cf', f"{params['Cf']}p")

        logger.debug("Параметры редактора установлены, запуск LTspice...")

        runner = SimRunner(simulator=self.ltspice_exe, output_folder=str(self.temp_dir))
        task = runner.run(editor)
        runner.wait_completion()

        self.raw_file = task.raw_file
        self.log_file = task.log_file

        if not self.raw_file or not self.log_file:
            raise RuntimeError("LTspice не сгенерировал .raw или .log файлы")

        logger.info(f"Симуляция завершена. raw: {self.raw_file}")
        return self.raw_file, self.log_file

    def export_raw_to_csv(self, raw_path: str, name: str = "ada4870") -> Path:
        logger.info(f"Экспорт данных из {raw_path}...")
        raw = RawRead(raw_path)

        time_trace = raw.get_trace('time')
        if time_trace is None:
            raise ValueError("В .raw файле не найдена ось времени (time)")

        data = {'Time': time_trace.get_wave()}
        for trace_name in raw.get_trace_names():
            if trace_name.lower() == 'time':
                continue
            trace = raw.get_trace(trace_name)
            if trace is not None:
                data[trace_name] = trace.get_wave()
                logger.debug(f"  Извлечён сигнал: {trace_name} ({len(data[trace_name])} точек)")

        df = pd.DataFrame(data)
        csv_path = self.output_dir / f"{name}_raw_export.csv"
        df.to_csv(csv_path, index=False)
        logger.info(f"CSV сохранён: {csv_path}")
        return csv_path

    @staticmethod
    def get_thd(log_path: str) -> str:
        thd = "N/A"
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "Total Harmonic Distortion:" in line:
                    thd = line.split(":")[-1].strip()
        logger.debug(f"THD из лога: {thd}")
        return thd

    @staticmethod
    def get_fourier_data(log_path: str) -> tuple[list[int], list[float]]:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        blocks = content.split("Fourier components of")
        if len(blocks) < 2:
            logger.warning("В логе не найден Фурье-анализ")
            return [], []

        last_block = blocks[-1]
        harmonics = []
        amplitudes = []
        pattern = r"^\s+(\d+)\s+[\d\.eE\+\-]+\s+([\d\.eE\+\-]+)"
        for m in re.finditer(pattern, last_block, re.MULTILINE):
            harmonics.append(int(m.group(1)))
            amplitudes.append(float(m.group(2)))

        logger.debug(f"Извлечено {len(harmonics)} гармоник")
        return harmonics, amplitudes

    def degradation_sweep(self, chosen_params: dict, frequencies: list[float],
                        show_progress: bool = True) -> list[float]:
        thd_values = []
        for freq in frequencies:
            if show_progress:
                logger.info(f"Сканирование частоты {freq/1e6:.2f} МГц")
            self.run(chosen_params, freq)
            thd_str = self.get_thd(self.log_file)
            try:
                thd_val = float(thd_str.replace('%', ''))
            except ValueError:
                thd_val = None
                logger.warning(f"Не удалось извлечь THD для {freq} Гц")
            thd_values.append(thd_val)
            if show_progress:
                logger.info(f"  THD = {thd_str}")

        output_path = Path(self.output_dir / "thd_vs_freq.csv")
        df = pd.DataFrame({'Frequency_Hz': frequencies, 'THD_%': thd_values})
        df.to_csv(output_path, index=False)

        return thd_values
