# src/timeseries_runner.py
from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Optional, Sequence, Dict, Any
from tqdm import tqdm

class TimeSeriesHeatPumpRunner:
    """
    Object-oriented runner that reads heat source/sink sheets, sets boundary conditions
    on a HeatPumpModel instance and runs off-design solves for each hour (or a single step).
    """

    def __init__(self,
                 model,                     # instance of your HeatPumpModel
                 file_path: str,
                 sheet_source: str = "Heat source",
                 sheet_sink: str = "Heat sink"):
        self.model = model
        self.file_path = file_path
        self.sheet_source = sheet_source
        self.sheet_sink = sheet_sink

        # placeholders for data and detected column names
        self.df_source: Optional[pd.DataFrame] = None
        self.df_sink: Optional[pd.DataFrame] = None
        self.cols: Dict[str, str] = {}
        self.results: Optional[pd.DataFrame] = None

    # ---------- utilities ----------
    @staticmethod
    def _find_col(df: pd.DataFrame, candidates: Sequence[str]) -> str:
        """Find a candidate column in df. Try exact, then substring, case-insensitive."""
        for c in candidates:
            if c in df.columns:
                return c
        # fallback
        cand_clean = [cand.strip('[]').lower() for cand in candidates]
        for col in df.columns:
            col_l = col.lower()
            for cc in cand_clean:
                if cc in col_l:
                    return col
        raise KeyError(f"No column found among {candidates} in dataframe columns: {list(df.columns)}")

    def load_data(self):
        """Read Excel sheets into dataframes."""
        self.df_source = pd.read_excel(self.file_path, sheet_name=self.sheet_source)
        self.df_sink   = pd.read_excel(self.file_path, sheet_name=self.sheet_sink)

    def detect_columns(self):
        """Detect commonly-named columns (robust to small typos)."""
        if self.df_source is None or self.df_sink is None:
            raise RuntimeError("Call load_data() before detect_columns().")

        # source sheet
        self.cols['t_in_src']  = self._find_col(self.df_source, ['T_in[degC', 'T_in[degC]'])
        self.cols['t_out_src'] = self._find_col(self.df_source, ['T_out[degC', 'T_out[degC]'])
        # pressure and flow might be missing; try graceful detection
        try:
            self.cols['p_src'] = self._find_col(self.df_source, ['P[bar]', 'P[bar]'])
        except KeyError:
            self.cols['p_src'] = None
        try:
            self.cols['flow_src'] = self._find_col(self.df_source, ['flow[kg/s]', 'flow'])
        except KeyError:
            self.cols['flow_src'] = None

        # sink sheet
        self.cols['t_in_sink']  = self._find_col(self.df_sink, ['T_in[degC', 'T_in[degC]'])
        self.cols['t_out_sink'] = self._find_col(self.df_sink, ['T_out[degC', 'T_out[degC]'])
        try:
            self.cols['p_sink'] = self._find_col(self.df_sink, ['P[bar]', 'P[bar]'])
        except KeyError:
            self.cols['p_sink'] = None
        try:
            self.cols['energy'] = self._find_col(self.df_sink, ['Energy[kWh]', 'Energy'])
        except KeyError:
            self.cols['energy'] = None

    # ---------- core methods ----------
    def _set_boundary_conditions_for_row(self, i: int):
        """Set network connection attributes for a single row index i."""
        # read values with safe fallbacks
        s = self.df_source
        k = self.cols
        # source values
        t_in_src  = float(s.loc[i, k['t_in_src']])
        t_out_src = float(s.loc[i, k['t_out_src']])
        p_src     = float(s.loc[i, k['p_src']]) if k.get('p_src') and pd.notna(s.loc[i, k['p_src']]) else None
        flow_src  = float(s.loc[i, k['flow_src']]) if k.get('flow_src') and pd.notna(s.loc[i, k['flow_src']]) else None

        # sink values
        t_in_sink  = float(self.df_sink.loc[i, k['t_in_sink']])
        t_out_sink = float(self.df_sink.loc[i, k['t_out_sink']])
        p_sink     = float(self.df_sink.loc[i, k['p_sink']]) if k.get('p_sink') and pd.notna(self.df_sink.loc[i, k['p_sink']]) else None
        energy_kwh = float(self.df_sink.loc[i, k['energy']]) if k.get('energy') and pd.notna(self.df_sink.loc[i, k['energy']]) else None

        # set cold-side (connections "11","12")
        conn11 = self.model.nwk.get_conn("11")
        conn12 = self.model.nwk.get_conn("12")
        # set fluid for water side and attributes
        try:
            conn11.set_attr(fluid={"water":1}, T=t_in_src)
            if p_src is not None:
                conn11.set_attr(p=p_src)
            if flow_src is not None:
                conn11.set_attr(m=flow_src)
            conn12.set_attr(T=t_out_src)
        except Exception as e:
            raise RuntimeError(f"Failed to set cold-side attrs at row {i}: {e}")

        # set hot-side (connections "21","22")
        conn21 = self.model.nwk.get_conn("21")
        conn22 = self.model.nwk.get_conn("22")
        try:
            conn21.set_attr(fluid={"water":1}, T=t_in_sink)
            if p_sink is not None:
                conn21.set_attr(p=p_sink)
            conn22.set_attr(T=t_out_sink)
        except Exception as e:
            raise RuntimeError(f"Failed to set hot-side attrs at row {i}: {e}")

        # evaporator: let solver compute duty (unless you want to set)
        self.model.ev.set_attr(Q=None)

        # set condenser Q if available (convert kWh->W and apply sign convention similar to design)
        if energy_kwh is not None:
            # IMPORTANT: your model used negative Q for condenser in design -> keep consistent
            Q_cond_W = - (energy_kwh * 1000.0)
            self.model.cd.set_attr(Q=Q_cond_W)

        # return a dict of inputs for logging
        return {
            "T_source_in": t_in_src, "T_source_out": t_out_src, "P_source_bar": p_src, "flow_source_kg_s": flow_src,
            "T_sink_in": t_in_sink, "T_sink_out": t_out_sink, "P_sink_bar": p_sink, "Energy_kWh": energy_kwh
        }

    def _solve_single(self, i: int) -> Dict[str, Any]:
        """Perform one off-design solve for row i and return results dict."""
        inputs = self._set_boundary_conditions_for_row(i)
        try:
            res = self.model.solve_offdesign(conn="11", T_source_in=inputs["T_source_in"], Q_evap=None)
        except Exception as exc:
            # solver failed — return NaNs but keep inputs
            res = {"COP": np.nan, "P_comp": np.nan, "Q_evap": np.nan, "Q_cond": np.nan}
            print(f"[warn] solver failed at row {i}: {exc}")
        out = {**inputs,
               "COP": res.get("COP", np.nan),
               "P_comp_W": res.get("P_comp", np.nan),
               "Q_evap_W": res.get("Q_evap", np.nan),
               "Q_cond_W": res.get("Q_cond", np.nan)}
        return out

    def run_one(self, row_idx: int = 0) -> pd.DataFrame:
        """Run a single timestep (useful for debugging). Returns a DataFrame with 1 row."""
        if self.df_source is None or self.df_sink is None:
            self.load_data()
            self.detect_columns()

        # ensure design solved
        self.model.solve_design()

        out = self._solve_single(row_idx)
        df = pd.DataFrame([out])
        self.results = df
        # convenience columns in kW
        self._postprocess_results()
        return self.results

    def run_all(self, show_progress: bool = True) -> pd.DataFrame:
        """Run all timesteps in the source dataframe."""
        if self.df_source is None or self.df_sink is None:
            self.load_data()
            self.detect_columns()
        # ensure design solved
        self.model.solve_design()

        n = len(self.df_source)
        rows = []
        iterator = range(n)
        if show_progress:
            iterator = tqdm(iterator, desc="Running off-design")
        for i in iterator:
            rows.append(self._solve_single(i))

        self.results = pd.DataFrame(rows)
        self._postprocess_results()
        return self.results

    def _postprocess_results(self):
        if self.results is None:
            return
        # convert W -> kW for convenience
        for col in ("P_comp_W", "Q_evap_W", "Q_cond_W"):
            if col in self.results.columns:
                self.results[col.replace("_W", "_kW")] = self.results[col] / 1000.0

    def save_results(self, path: str = "hp_offdesign_results.csv"):
        if self.results is None:
            raise RuntimeError("No results to save. Run run_one or run_all first.")
        self.results.to_csv(path, index=False)

    def get_results(self) -> pd.DataFrame:
        if self.results is None:
            raise RuntimeError("No results available yet.")
        return self.results
