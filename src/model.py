from tespy.networks import Network
from tespy.components import (Compressor, HeatExchanger, Condenser,
                              Valve, CycleCloser, Source, Sink)
from tespy.connections import Connection
from CoolProp.CoolProp import PropsSI as PSI

class HeatPumpModel:
    def __init__(self, working_fluid):
        self.working_fluid = working_fluid
        self.nwk, self.ev, self.cd, self.cp = self._build_network()
    
    def _build_network(self):
        nwk = Network(p_unit="bar", T_unit="C", h_unit="kJ/kg", m_unit="kg/s", iterinfo=False)
        
        cp = Compressor("compressor")
        ev = HeatExchanger("evaporator")
        cd = Condenser("condenser")
        va = Valve("expansion valve")
        cc = CycleCloser("cycle closer")
        so1 = Source("ambient water source")
        si1 = Sink("ambient water sink")
        so2 = Source("heating water source")
        si2 = Sink("heating water sink")
        
        # refrigerant cycle
        c0 = Connection(va, "out1", cc, "in1", label="0")
        c1 = Connection(cc, "out1", ev, "in2", label="1")
        c2 = Connection(ev, "out2", cp, "in1", label="2")
        c3 = Connection(cp, "out1", cd, "in1", label="3")
        c4 = Connection(cd, "out1", va, "in1", label="4")
        nwk.add_conns(c0, c1, c2, c3, c4)
        
        # cold-side (heat source) loop
        c11 = Connection(so1, "out1", ev, "in1", label="11")
        c12 = Connection(ev, "out1", si1, "in1", label="12")
        # hot-side (heat sink) loop
        c21 = Connection(so2, "out1", cd, "in2", label="21")
        c22 = Connection(cd, "out2", si2, "in1", label="22")
        nwk.add_conns(c11, c12, c21, c22)
        

        # In our system, the heating-water feed temperature is 40 °C (c21). A good guess for pressure
        # can be obtained from CoolProp’s PropsSI function. Therefore, 
        # We choose a condensing temperature of ~90 °C. We can set the pressure to a slightly 
        # higher value of that temperature’s corresponding condensation pressure (=273.15+95 K) as a starting guess, 
        # then convert to bar units. This gives sufficient driving temperature difference for the
        # heat transfer in the condenser.
        p_cond = PSI("P", "Q", 1, "T", 273.15 + 95, self.working_fluid) / 1e5

        # At connection c3 (compressor outlet → condenser inlet):
        # We set a guess for the refrigerant temperature (T = 170 °C).
        # Reasoning:
        # - Following the TESPy tutorial “Build a Heat Pump Stepwise”, the condenser inlet
        #   temperature must be above the consumer feed‐flow temperature to ensure
        #   sufficient driving temperature difference.  https://tespy.readthedocs.io/en/main/tutorials/heat_pump_steps.html
        # - In our system, the heating‐water feed upstream of the condenser is 40 °C.
        #   Therefore we choose a significantly higher refrigerant temperature of 170 °C
        #   to provide “temperature head” for heat transfer.
        # - This value is a starting guess for the solver (design mode); actual cycle will
        #   compute the final condensing pressure based on this and the fluid properties.
        # - Once design solution converges, one might adjust this guess or replace it with
        #   a more physically‐consistent parameter (e.g., a fixed terminal temperature difference).
        c3.set_attr(T=170, p=p_cond, fluid={self.working_fluid: 1})
        
        # design duty values
        Q_design_cd = -1012e3     # W
        Q_design_ev = -1000e3     # W
        
        # set component design attributes, pr=1 for simplicity
        cp.set_attr(eta_s=0.85)
        cd.set_attr(Q=Q_design_cd, pr1=1, pr2=1)
        ev.set_attr(Q=Q_design_ev, pr1=1, pr2=1)
        
        # set connection (cold & hot loops) boundary conditions
        T_ambient_design = 40.0   # °C
        c11.set_attr(fluid={"water": 1}, p=1.0, T=T_ambient_design)
        c12.set_attr(T=10.0)
        c21.set_attr(fluid={"water": 1}, p=4.0, T=40.0)
        c22.set_attr(T=90.0)
        
        return nwk, ev, cd, cp
    
    def solve_design(self):
        self.nwk.solve("design")
        self.nwk.save("design_state.json")
        self.nwk.print_results()
    
    def solve_offdesign(self, conn: str, T_source_in=None, Q_evap=None):
        # Modify boundary conditions if provided
        if T_source_in is not None:
            self.nwk.get_conn(conn).set_attr(T=T_source_in)
        if Q_evap is not None:
            self.ev.set_attr(Q=Q_evap)
        # Solve off-design using stored design state
        self.nwk.solve("offdesign", design_path="design_state.json")
        # self.nwk.print_results()
        # Extract results
        COP = abs(self.cd.Q.val) / self.cp.P.val
        P_comp = self.cp.P.val
        Q_evap_actual = self.ev.Q.val
        Q_cond_actual = self.cd.Q.val
        return {
            "COP": COP,
            "P_comp": P_comp,
            "Q_evap": Q_evap_actual,
            "Q_cond": Q_cond_actual
        }
    

