# ADASim — Calculation and Simulation of the AD9705 → ADA4807-2 → ADA4870 Signal Path

A tool for component selection and LTspice verification of the output stage of a sinusoidal signal generator: DAC (AD9705) → transimpedance stage (ADA4807-2) → high-current buffer (ADA4870). Used in the HiPIMS generator anode driver project (Bauman MSTU laboratory).

## Why This Tool Exists

There are three specific tasks that are time-consuming and error-prone to do manually:

1. **Select Ra/Rf/Rb/Cf values** for a target amplitude and load current, rounded to the real E96 series — so you don't have to recalculate each time in a notebook.
2. **Run a realistic LTspice simulation** with these values and extract THD, waveform shape, and harmonic spectrum — without manually opening the GUI for each variant.
3. **Parse the circuit itself (.asc)** and produce a readable list of "which pin of which component is connected to which net" — without manual coordinate tracing, which has previously led to incorrect conclusions (see the "Gain Asymmetry" section below for the story of how it was once misdiagnosed precisely due to the lack of such a tool).

## What the Signal Path Actually Does

```
AD9705 (DAC, complementary current outputs IOUTA/IOUTB)
        │
        ▼
ADA4807-2 × 2 (TIA — transimpedance stage, current → voltage)
   Rfn/Rfp = R_TIA — sets the transimpedance (currently 249Ω = R17/R18 on the board)
        │
        ▼  (differential voltage OUTA/OUTB)
Ra/Rb/Rf/Cf — matching network at the ADA4870 inputs
        │
        ▼
ADA4870 (high-current buffer, ±18V, up to 1A output current)
        │
        ▼
SIGNAL → load (Rload = 22Ω = R23 on the board)
```

Target parameters (see `config.yaml` → `params`): output amplitude ~14V, load 22Ω (peak current ~0.6A), ±18V supply.

## Gain Asymmetry Between the Two Rails (~6-7%)

**Observation:** In both simulation and on the actual board, the positive and negative peaks of the output signal are not equal in magnitude (e.g., +13.7V vs −14.9V with Ra=150Ω/Rf=2100Ω).

**Why this is NOT a selection bug.** `calculation.py` computes `Rb = Ra·Rf/(Ra+Rf)` — this is the classic formula for input bias current matching: it equalizes the DC resistance seen by each op-amp input, thereby removing offset caused by input bias current. It does **not** participate in the AC gain loop and cannot correct the gain difference between the rails.

**Where the difference actually comes from.** The circuit has a single feedback resistor (`Rf`) on the inverting input of the ADA4870, and a series resistor (`Rb`) on the non-inverting input (no shunt resistor to ground). The transfer coefficients for this topology are:

```
A_v(inv.)   = -Rf/Ra
A_v(non-inv.) = 1 + Rf/Ra
```

The difference between them is always exactly **1** in magnitude — this is a topological property of circuits with a single feedback resistor, independent of the specific Ra/Rf/Rb values. For a target A_v≈14, the discrepancy (14 vs 15, roughly) gives the observed ~6-7%.

**Status:** Considered acceptable for the application (headroom to supply rails ±16V with target amplitude 14V — far from clipping both up and down) and consciously left uncompensated. If compensation becomes necessary in the future — it should be done by shifting the target `A_v` (essentially aiming not strictly at 14V, but at the midpoint between the future +/- peaks), not by tweaking Ra/Rb, which are not designed for this and physically cannot affect it.

**The backstory, if you're curious how we got here:** In the early stages, when manually tracing the `.asc` coordinates, resistor `Rb` was mistaken for a "floating" resistor (open circuit) due to the anomalously low current in the CSV (~9µA vs ~6.6mA for `Ra`). It turned out this wasn't an open circuit but normal behavior — `Rb` is indeed a series resistor, but in the high-impedance non-inverting input path, where bias current flows in microamps by definition, unlike `Ra`, which sits in the low-impedance summing node (inv. input + `Rf`). This confusion was exactly the reason for writing a proper automatic circuit parser instead of manual coordinate tracing — see `ltspice_io/`.

## Installation

```bash
pip install -r requirements.txt
```

Requires LTspice (path to `.exe` — in `config.yaml` → `ltspice.executable`).

## Usage

```bash
python main.py
```

Everything is configured via `config.yaml`:

- `params` — target signal path parameters (amplitude, current, R_TIA, Ra range)
- `frequencies` — frequency grid for THD degradation sweeps
- `plots` — which plots to generate and whether to save/show
- `schematic.symbol_search_paths` — where to look for `.asy` symbols (see below)

Results go to `images/` (plots, `report.txt`, CSV) and `net/` (readable circuit report).

## Configuration Parameters (`config.yaml`)

### `schematic`
| Parameter | Purpose |
|---|---|
| `path` | Path to the `.asc` schematic file |
| `symbol_search_paths` | List of directories to search for `.asy` files for each symbol in the schematic (both custom ones like `OpAmps\ADA4870` and standard primitives like `res`/`cap`/`voltage`/`bi`). Must include the folder with project custom symbols; standard primitives are usually in `<LTspice>\lib\sym` |

### `ltspice`
| Parameter | Purpose |
|---|---|
| `executable` | Path to `LTspice.exe`, needed to run simulations via `PyLTSpice` |

### `simulation`
| Parameter | Purpose |
|---|---|
| `output_dir` | Where to store CSV/plots/report (default `./out`) |
| `temp_dir` | Working folder for `.raw`/`.log` files from LTspice (default `./temp`) |

### `params` — Input Data for Component Calculation
| Parameter | Purpose |
|---|---|
| `I_FS` | Full-scale DAC current, A. For AD9705, set by resistor `R19` (`DAC_FS_ADJ`) on the board |
| `R_TIA` | Transimpedance of the TIA stage, Ω. On the board — `R17`/`R18` |
| `V_out_amp` | Target amplitude at the ADA4870 output, V |
| `R_load` | Load resistance, Ω. On the board — `R23` |
| `V_sup` | ADA4870 supply voltage (symmetrical, ±), V |
| `V_headroom` | Required headroom from supply rail at maximum amplitude, V |
| `I_out_max` | Maximum allowable output current of ADA4870 per datasheet, A |
| `Rf_max` | Upper limit for `Rf` during search — filters out unrealistic combinations |
| `Ra_candidates` | List of `Ra` values (usually from E96/E24 series) to iterate over during selection |
| `C_in_parasitic` | Parasitic input capacitance of ADA4870 (per datasheet), used to calculate compensating `Cf` |
| `Rf_target` | Desired `Rf` value "for aesthetics"/repeatability between revisions — used only as a sorting criterion, not a constraint |

### `frequencies`
List of frequencies (Hz) at which THD is swept when `plots.degradation: true`
(see `degradation_sweep` in `runner.py`).

### `tran_settings`
| Parameter | Purpose |
|---|---|
| `periods_transient` | How many signal periods to "warm up" before starting to save data (transient settling) |
| `periods_analysis` | How many periods after warm-up to actually save and analyze |
| `points_per_period` | Sampling density per period — affects both FFT accuracy and `.raw`/CSV size |

### `plots`
| Parameter | Purpose |
|---|---|
| `time_domain` / `spectrum` / `degradation` / `input_currents` | Which plots to generate (see `report/plotting.py`) |
| `save` | Whether to save plots to files in `output_dir` |
| `show` | Whether to display plots interactively (`plt.show()`) — usually `false` for automated runs, otherwise blocks execution on each plot |

### `netlist_generator`
| Parameter | Purpose |
|---|---|
| `generate_netlist` | Whether to build a readable circuit report (`ltspice_io/readable_report.py`) |
| `output_dir` | Where to save `*_readable.txt` (default `./net`) |

### `ac_analysis`
Reserved for future AC sweep (`freq_start`/`freq_stop`/
`points_per_decade`) — at the time of writing this README, not yet connected to any run in `main.py`, but parameters are already read from config for future use.

## How Component Values Are Calculated (Algorithm in `core/calculation.py`)

The calculation in `select_components()` proceeds in several steps:

1. **Power supply constraint check.** If the requested `V_out_amp` exceeds `|V_sup| − V_headroom` (i.e., doesn't fit in the supply rail with the required headroom), the amplitude is automatically reduced to the maximum possible, and a warning is logged — the calculation doesn't crash, it adapts.

2. **Current constraint check.** Peak current `V_out_amp / R_load` is compared with `I_out_max`; if exceeded — this is NOT automatically adjusted (unlike voltage excess, current excess is considered a more serious error that could physically damage the ADA4870, so the calculation doesn't try to guess a "safe" value on its own).

3. **Calculate required gain.** Differential voltage at the TIA output `V_diff_amp = I_FS · R_TIA`, required buffer gain `A_v_required = V_out_amp / V_diff_amp`.

4. **Iterate over `Ra_candidates`.** For each candidate `Ra` from config:
   - `Rf = A_v_required · Ra` (exact, pre-rounding value)
   - Round `Rf` and the derived `Rb = Ra·Rf/(Ra+Rf)` to the nearest **E96** series value (`nearest_e96()` — takes the mantissa, finds the closest mantissa in the E96 table by absolute difference, applies the order of magnitude back)
   - Calculate compensating capacitance `Cf = C_in_parasitic · (Ra / Rf_e96)` — standard pole compensation for the pole introduced by ADA4870's input capacitance together with `Rf`
   - Candidates with `Rf` above `Rf_max` are discarded as unrealistic

5. **Sort results.** For each variant, compute:
   - `Rb_error_abs` — how far the E96 rounding pulled `Rb` from the exact calculated value
   - `Rf_error_rel` — relative deviation of the rounded `Rf` from `Rf_target` (this is a "soft" preference criterion, not a constraint)

   Final sorting — first by `Rb_error_abs` (input bias current matching accuracy is more important), then by `Rf_error_rel` (closeness to the target "familiar" value — secondary). The first (best) result is selected.

**Important about the physical meaning of `Rb`.** This is input bias current matching (`Rb = Ra‖Rf`), NOT rail gain balancing — see the "Gain Asymmetry" section above for why a DC offset of about `R_TIA·I_FS/2` remains at the output, which this algorithm fundamentally does not eliminate (and shouldn't — that's not its job).

## Circuit Description (`ada4807_4870.asc`)

![ADA4807-2 - ADA4870 Schematic](images/scheme.png)

A full automatically generated pin/net list is in [`net/ada4807_4870_readable.txt`](ada4807_4870_readable.txt) (see `ltspice_io/readable_report.py`). Here — the meaning of each block:

### Signal Sources (DAC Emulation)
`IOUTA`/`IOUTB` — behavioral current sources (`bi`), emulating the complementary current outputs of the AD9705:
```
IOUTA = IFS/2 + (IFS/2)·sin(2π·FREQ·t)
IOUTB = IFS/2 + (IFS/2)·sin(2π·FREQ·t + π)
```
Note: `IOUTA + IOUTB = IFS = const` — they are not strictly out of phase around zero, but oscillate around `IFS/2` in antiphase. This is exactly what creates the common-mode DC current component that manifests as offset at the output (see the symmetry section above).

### TIA Stage (`U2`, `U3` — ADA4807-2)
Two identical channels, one for each DAC current:
- Non-inverting input (pin 100) — tied to GND (net `0`) for both
- Inverting input (pin 101) — takes current from `IOUTA`/`IOUTB` (nets `INN`/`INP`), feedback `Rfn`/`Rfp` (= `R_TIA`) also connected here
- Output (pin 104) — node `N_-656_-144` (channel A) / `N_-656_272` (channel B); synthetic name because no explicit `FLAG` is attached to this node in the schematic — essentially "just U2/U3 output", the author didn't give it a meaningful name
- Supply — ±2.5V (`P2V5`/`N2V5`), separate from the main ADA4870 supply (±18V) — TIA runs at lower swing

### Matching Network Before ADA4870
- `Ra` — from U2 output (`N_-656_-144`) to node `OUTA` (= inv. input U1)
- `Rb` — from U3 output (`N_-656_272`) to node `OUTB` (= non-inv. input U1)
- `Rf` — U1 feedback: from `SIGNAL` (output) back to `OUTA`
- `Cf` — in parallel with `Rf`, input capacitance compensation for U1

### Current Buffer (`U1` — ADA4870)
Pins (see `PINATTR PinName` in `ADA4870.asy` — numeric placeholder names, not alphabetical):
| Pin | Net Name | Function |
|---|---|---|
| 100 | `OUTB` | Non-inverting input |
| 101 | `OUTA` | Inverting input |
| 102 | `VDD` | +18V |
| 103 | `VEE` | −18V |
| 104 | `SIGNAL` | Output |
| 106 | `SD` | Control (see `R1`/`R2` — voltage divider setting a DC bias on this pin; in hardware, a comparator with hysteresis on LM311 is used instead of the resistive divider, this part is simplified in the LTspice model) |

### Load
`Rload` (= target `R_load` from config) and `Cload` — from `SIGNAL` to ground, emulating the real load of the signal path.

## What `report.txt` Contains and Why

Generated by `report/text_report.py`, sections from top to bottom:

1. **Input parameters** — direct echo of what's set in `config.yaml → params`, so the report is self-contained (no need to refer back to the config separately if the result is discussed later without it).

2. **Calculation results** — `V_diff_amp` and required gain `A_v` before E96 rounding. Needed to check whether the final `A_v_real` has drifted too far from the ideal due to rounding.

3. **Selected component values** — final `Ra`/`Rf`/`Rb`/`Cf`, both exact calculation and rounded (E96). The difference between them is the `Rb_error_abs`/`Rf_error_rel` used for sorting (see algorithm above); if it's large, check whether there's a candidate in `Ra_candidates` that yields smaller error.

4. **Verification** — `A_v_real` (with rounded values), expected output amplitude, and peak load current. This is what should be compared with the actual waveform in `time_domain.png` — if it diverges by more than a few percent, something is wrong not in the calculation but in the circuit/simulation itself.

5. **Known topology feature** — a short version of the gain asymmetry section from this README, so it's visible with every run, not just when reading the documentation separately.

6. **Simulation results** — THD at the first (reference) frequency from `frequencies`. The full sweep across all frequencies is in `thd_vs_freq.csv`; only one point goes into `report.txt` to keep it short and readable at a glance.

7. **Files** — paths to all associated artifacts (CSV, LTspice log, readable circuit report) for quick navigation if `report.txt` is sent separately from the rest of the `images/` folder.

## Plot Descriptions (`report/plotting.py`)

All four are built from the same CSV (`ada4870_raw_export.csv`), except `degradation.png`, which is built from a separate sweep.

### `time_domain.png` — `plot_time_domain()`
Two stacked plots: `V(signal)` (output voltage) on top, `I(Rload)` (load current) on bottom, shared time axis. The main purpose is to visually check the waveform: no clipping against supply rails, no visible distortion, and to compare peak values with what `report.txt` predicts (`A_v_real`, expected amplitude). This is exactly where the +/- peak asymmetry is visible, discussed separately in the asymmetry section above.

![Signal Voltage/Current](images/time_domain.png)

### `spectrum.png` — `plot_spectrum()`
Bar chart of the first 10 harmonic amplitudes (log Y scale), data from the `.four` block in the LTspice log. The title duplicates the THD. Purpose — to see which harmonics contribute most to distortion: even harmonics (2, 4, 6...) typically indicate signal asymmetry (uneven shape distortion), odd harmonics (3, 5, 7...) indicate symmetric limiting/compression (e.g., approaching clipping). In practice, our dominant contribution comes from odd harmonics — meaning the distortion source is not the same effect that gives offset/peak asymmetry; these are two different, unrelated phenomena.

![Signal Spectrum](images/spectrum.png)

### `input_currents.png` — `plot_input_currents()`
Currents `IOUTA`/`IOUTB`, reconstructed by back-calculation from voltages across the TIA resistors (`(V(n001)-V(inn))/R_TIA`) — i.e., not measured directly, but computed. Purpose — to verify that the behavioral DAC current sources behave as intended (complementary, with common-mode offset IFS/2, no unexpected glitches) before digging into distortion further down the chain — if the problem is already visible here, it won't be found further along.

![Currents](images/input_currents.png)

### `degradation.png` — `plot_degradation()`
THD (%) vs frequency (log X scale), one point for each frequency in `frequencies` from config. Built by a separate run (`degradation_sweep()` in `runner.py`), not from a single CSV — each point is a separate LTspice run at its own frequency. Purpose — to verify that distortion doesn't grow unacceptably at the upper end of the operating range. Important: THD does not show offset/peak asymmetry (that's "zero-order harmonic," not included in `.four` calculation) — for frequency-dependent symmetry monitoring this plot is not suitable; you need to separately look at `V(signal).min()/max()` at each frequency (see asymmetry section above, where it's noted this isn't implemented yet).

![THD](images/degradation.png)

#### How to Get Realistic THD?

Zero THD is not a parsing error, but a consequence of **ideal models**. To make the simulation show real distortion (say, 0.01–0.1% at high frequencies), you need to:

##### 1. Replace op-amp macromodels with transistor-level models
The circuit uses:

```
C:\Users\grand\AppData\Local\LTspice\lib\sub\ADA4807.sub
C:\Users\grand\AppData\Local\LTspice\lib\sub\ADA4870.lib
```

These are standard macromodels. Replace them with **transistor-level** models (usually have a `_TR` suffix). (Download from Analog Devices website.) In the `.asc` file, change symbol names:
- `OpAmps\\ADA4870` → `OpAmps\\ADA4870_TR`
- `OpAmps\\ADA4807-2` → `OpAmps\\ADA4807-2_TR`

##### 2. Add nonlinearity to the signal source

Currently — an ideal sine wave:

```
I = {IFS/2 + (IFS/2)*sin(2*pi*FREQ*time)}
```

Add a small third harmonic to emulate DAC nonlinearity:

```
I = {IFS/2 + (IFS/2)*(sin(2*pi*FREQ*time) + 1e-4*sin(3*2*pi*FREQ*time))}
```

This will give THD around 0.01% — already more realistic.

##### 3. Increase simulation resolution

In `config.yaml` set:
```yaml
tran_settings:
  periods_transient: 20
  periods_analysis: 20
  points_per_period: 5000
```

This reduces numerical artifacts and makes harmonic calculation more accurate.

##### 4. Parse Partial Harmonic Distortion instead of Total

In `runner.py`, method `get_thd()`:

```python
@staticmethod
def get_thd(log_path: str) -> str:
    thd = "N/A"
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if "Partial Harmonic Distortion:" in line:  # instead of Total
                thd = line.split(":")[-1].strip()
    logger.debug(f"THD from log: {thd}")
    return thd
```

Then you'll get about 0.000004%. At least not zero...

##### 5. (Optional) Add parasitic inductances and ESR

Add small inductances (1–10 nH) in series with outputs and ESR resistors (0.1–1 Ω) for capacitors — this will bring the model closer to the real board.

---

## Architecture

```
adasim/
├── core/                    # Pure logic, NO side effects and NO I/O
│   ├── calculation.py        # Ra/Rf/Rb/Cf selection, E96 rounding
│   └── constants.py          # E96 series
│
├── ltspice_io/               # Everything that reads LTspice files and runs the simulator
│   ├── asy_parser.py          # .asy parsing (coordinates + symbol pin names)
│   ├── asc_parser.py          # .asc parsing (WIRE/FLAG/SYMBOL → net graph)
│   ├── readable_report.py     # Human-readable circuit report (from asc_parser)
│   └── runner.py              # LTspiceRunner — subprocess, .raw/.log, THD/Fourier
│
├── report/                   # Result presentation
│   ├── plotting.py            # Plots (save to file, optionally show())
│   └── text_report.py         # Text report.txt
│
├── config.py                 # YAML config loader
├── config.yaml
├── logger_config.py           # 'ADASim' logger, unchanged during refactoring
├── main.py                    # Orchestration only, no logic
├── docs/known_issues.md       # Asymmetry details and pitfalls
└── requirements.txt
```

**Separation principle:** `core/` knows nothing about LTspice — pure functions from `params: dict` to component values, testable without a single `.asc` file. `ltspice_io/` — all code that works with LTspice files (symbols, schematics, netlist, simulator execution), knows nothing about how component values are selected. `report/` only plots and formats what's passed to it, doesn't make decisions about values. `main.py` ties everything together and should remain thin — if real logic appears in it (not a call to another function), that's a signal it should move to `core/` or `ltspice_io/`.

### Why Parse `.asc` Directly Instead of Using `LTspice -netlist`

The old approach — running `LTspice -netlist` and parsing the resulting `.net` file — gives raw pin numbers (`pin104`, `pin106`) instead of real pin names (`IN+`, `OUT`, `SD`), and the ExpressPCB-style netlist table format is poorly documented and had to be reverse-engineered manually. `asc_parser.py` reads the original `.asc` directly and takes real pin names from `.asy` — the same level of detail visible in LTspice itself when hovering over a pin, but automated for the entire circuit at once.

### `.asy` File Encoding

Different `.asy` files appear both in UTF-16LE (typically custom symbols saved by LTspice through the GUI) and in plain ASCII/UTF-8 (standard primitives like `res.asy`). `asy_parser.py` detects encoding based on content (BOM, then proportion of null bytes), not by trial and error with exception handling — a plain ASCII file will almost always "successfully" but incorrectly decode as UTF-16LE, so relying on `UnicodeDecodeError` as an error indicator doesn't work here.

### Known Limitations

Full list in [`docs/known_issues.md`](docs/known_issues.md): besides gain asymmetry, it also covers that `.param` inside the `.asc` itself is not the source of truth (it's always overridden by `runner.py` before simulation), and a general note about `.asy` encodings.