
# Heat Pump TESPy Model — Design & Off-Design Simulation

> **Object-oriented TESPy heat pump model with time-series data & visualization**

## Overview

This project implements a **heat pump simulation tool** in Python using the
[TESPy](https://tespy.readthedocs.io/) library.

---

### Model Setup & Reference

The heat pump cycle is modeled as a **closed-loop vapor compression cycle** consisting of:

* **Compressor**
* **Condenser (heat sink)**
* **Expansion valve**
* **Evaporator (heat source)**

The evaporator and condenser are modeled as **heat exchangers**, with water streams on the secondary sides (for the heat source and sink).

The implementation is based on the TESPy heat pump tutorial:

🔗 [https://oemof.github.io/heat-pump-tutorial/model/tespy-partload-performance.html](https://oemof.github.io/heat-pump-tutorial/model/tespy-partload-performance.html)

![heat_pump_full](https://github.com/user-attachments/assets/5197f5d4-1540-4d4d-8184-1afb4b129fa6)


### Why this model?

This parametrization ensures:

* stable off-design solves
* control over thermal input/output at evaporator & condenser
* avoidance of singular Jacobians caused by over-specifying refrigerant states

This also makes the model reusable: you can plug in **any time series dataset** of temperatures + heat demand.

---


## Key Features

* Object-oriented
* Modular (easy to extend to other fluids or heat pump configs)
* Simulates design condition (provided conditions)
* Handles off-design simulation + dataset input 
* Visualization separated into its own class
* Compatible with any time-series dataset (hourly values)

---
## Model Architecture

```
src/
│
├── model.py                     → HeatPumpModel (TESPy network setup + design/offdesign)
├── run_timeseries.py            → TimeSeriesHeatPumpRunner (maps dataset → model inputs → results)
└── plots.py                → HeatPumpVisualizer (plots the results)

data/
└── HP_case_data.xlsx        → Provided dataset
│
Additional files (generated during runs)
├── design_state.json            → saved TESPy design state (used for offdesign solves)
├── system_design.json           → exported network configuration
└── hp_offdesign_timeseries.csv  → results from time-series runner
```

---

## How it Works

### **HeatPumpModel**

Responsible for:

* building TESPy network (compressor, condenser, valve, evaporator)
* setting design conditions
* executing `solve_design()` and `solve_offdesign()`

```python
from model import HeatPumpModel

model = HeatPumpModel(working_fluid="R134a")
model.solve_design()
```

---

### 2. **TimeSeriesHeatPumpRunner**

Reads the Excel dataset / maps:

| Dataset column                       | Applied to model                                |
| ------------------------------------ | ----------------------------------------------- |
| Heat source T_in, T_out, p, massflow | Connections `11` and `12` (evaporator side)     |
| Heat sink T_in, T_out, Energy[kWh]   | Connections `21` and `22` + condenser heat duty |

Each row = 1 hour → 1 off-design solve.

```python
from run_timeseries import TimeSeriesHeatPumpRunner

runner = TimeSeriesHeatPumpRunner(model, "../data/HP_case_data.xlsx")
df_all = runner.run_all()   # ⟵ runs whole dataset
runner.save_results("hp_timeseries.csv")
```

---

### 3. **Visualization**

```python
from plots import HeatPumpVisualizer

viz = HeatPumpVisualizer(figsize=(10, 12))
viz.plot_timeseries(df_all, title="Heat Pump Performance Over Time")
viz.save("hp_timeseries.png")
```

---


## Explanation of TESPy warnings during design and off-design simulations

### **“Solver behaviour and warnings (design + off-design)”**


When running the model under the **design conditions specified in the case**
( Q<sub>evap</sub> = –1000 kW, Q<sub>cond</sub> = –1012 kW, T<sub>source</sub>=40 → 10 °C, T<sub>sink</sub>=40 → 90 °C ), TESPy successfully solves the compressor, condenser and overall mass/energy balances.
However, TESPy reports warnings on the **evaporator** related to terminal temperature differences (TTD) and heat-exchanger effectiveness:

```
Invalid value for ttd_u / ttd_l / ttd_min  (value < 0)
Invalid value for eff_cold / eff_hot      (value < 0)
```

These messages indicate that, under the fixed design constraints, the internal heat-exchanger model cannot find a *physically feasible temperature approach* on the evaporator side. A negative TTD means that the cold stream would need to be warmer than the hot stream at some point inside the HX, which is thermodynamically impossible. The root cause is that at design we **fully fix the heat duty (Q), inlet and outlet temperatures**. This combination over-constrains the evaporator: TESPy has no flexibility left to adjust mass flow, approach temperature, or refrigerant superheat to achieve a realistic internal temperature profile.

Importantly:

* The **overall heat-pump balance is correct** (Q, P<sub>comp</sub>, COP are solved and consistent).
* The warnings do **not** indicate a coding error; they highlight that the fixed design targets are **physically aggressive / idealised**, leaving no degrees of freedom for the HX model to satisfy realistic temperature approaches.
* Similar warnings also appeared for some off-design time-steps in the time-series dataset, where the imposed boundary conditions temporarily push the system outside physically feasible operation.

---

## Outputs

The simulation produces:

| Metric      | Description                  |
| ----------- | ---------------------------- |
| `COP`       | Coefficient of Performance   |
| `P_comp_kW` | Compressor power consumption |
| `Q_evap_kW` | Heat absorbed from source    |
| `Q_cond_kW` | Heat delivered to sink       |

Example plot:

```
(COP over time)
(Compressor power)
(Q_evap + Q_cond)
```

---

## Installation

```bash
# create venv
python -m venv .venv
source .venv/bin/activate

# install requirements
pip install -r requirements.txt
```

---

## Run simulation

```bash
jupyter notebook running_functions_with_explanations.ipynb
```

Or directly from Python:

```python
model.solve_design()
df = runner.run_all()
viz.plot_timeseries(df)
```

