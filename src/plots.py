# src/visualiser.py
from __future__ import annotations
import matplotlib.pyplot as plt
import pandas as pd
from typing import Optional, Sequence


class HeatPumpVisualizer:
    """
    Visualiser for heat-pump timeseries results.

    Expected columns in df_results (names are flexible, see `colmap`):
      - time
      - COP
      - P_comp_kW
      - Q_evap_kW
      - Q_cond_kW

    The class will try to be robust if some columns are missing.
    """

    def __init__(self,
                 figsize: tuple[int, int] = (10, 12),
                 colmap: Optional[dict] = None):
        """
        colmap: optional mapping of logical names -> actual column names in df.
          Example:
            {"time": "time", "COP": "COP", "P_comp_kW": "P_comp_kW", ...}
        """
        self.figsize = figsize
        # default mapping (change if your df uses different names)
        self.colmap = colmap or {
            "time": "time",
            "COP": "COP",
            "P_comp_kW": "P_comp_kW",
            "Q_evap_kW": "Q_evap_kW",
            "Q_cond_kW": "Q_cond_kW"
        }
        self._last_fig = None

    def _col(self, df: pd.DataFrame, logical_name: str) -> Optional[Sequence]:
        """Return the series for logical_name or None if missing."""
        colname = self.colmap.get(logical_name)
        if colname is None:
            return None
        return df[colname] if colname in df.columns else None

    def plot_timeseries(self,
                        df_results: pd.DataFrame,
                        title: Optional[str] = None,
                        return_fig: bool = False,
                        tight: bool = True) -> Optional[plt.Figure]:
        """
        Draw a 3-row timeseries plot:
         1) COP
         2) Compressor power [kW]
         3) Q_evap [kW] and Q_cond [kW]

        Returns matplotlib.Figure if return_fig True (otherwise shows and returns None).
        """
        time = self._col(df_results, "time")

        cop = self._col(df_results, "COP")
        p_comp = self._col(df_results, "P_comp_kW")
        q_evap = self._col(df_results, "Q_evap_kW")
        q_cond = self._col(df_results, "Q_cond_kW")

        fig, axs = plt.subplots(3, 1, figsize=self.figsize, sharex=True)
        self._last_fig = fig

        # --- COP plot ---
        if cop is not None:
            axs[0].plot(time if time is not None else cop.index, cop, label="COP")
        else:
            axs[0].text(0.5, 0.5, "COP column missing", ha="center", va="center", transform=axs[0].transAxes)
        axs[0].set_ylabel("COP")
        axs[0].legend()
        axs[0].grid(True)

        # --- Compressor power ---
        if p_comp is not None:
            axs[1].plot(time if time is not None else p_comp.index, p_comp, label="Power (kW)")
            axs[1].set_ylabel("Compressor Power [kW]")
        else:
            axs[1].text(0.5, 0.5, "P_comp_kW column missing", ha="center", va="center", transform=axs[1].transAxes)
        axs[1].legend()
        axs[1].grid(True)

        # --- Heat transfer rates ---
        plotted = False
        if q_evap is not None:
            axs[2].plot(time if time is not None else q_evap.index, q_evap, label="Q Evaporator (kW)")
            plotted = True
        if q_cond is not None:
            axs[2].plot(time if time is not None else q_cond.index, q_cond, label="Q Condenser (kW)")
            plotted = True
        if not plotted:
            axs[2].text(0.5, 0.5, "Q_evap_kW / Q_cond_kW columns missing", ha="center", va="center", transform=axs[2].transAxes)
        axs[2].set_ylabel("Heat Transfer [kW]")
        axs[2].legend()
        axs[2].grid(True)

        # x label
        axs[-1].set_xlabel("Time")
        if title:
            fig.suptitle(title)
            # push down subplots if suptitle used
            fig.subplots_adjust(top=0.95)

        if tight:
            plt.tight_layout()

        if return_fig:
            return fig
        else:
            plt.show()
            return None

    def save(self, path: str, dpi: int = 200):
        """Save the last plotted figure to file (png/pdf)."""
        if self._last_fig is None:
            raise RuntimeError("No figure available. Call plot_timeseries() first.")
        self._last_fig.savefig(path, dpi=dpi, bbox_inches="tight")

