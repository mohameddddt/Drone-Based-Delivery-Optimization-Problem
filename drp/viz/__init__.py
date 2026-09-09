"""Visualisation: static figures and animated playback."""
from drp.viz.animate import animate_routes
from drp.viz.static import (plot_bnb_dual_gap, plot_convergence,
                            plot_gap_to_reference, plot_method_comparison,
                            plot_routes, plot_runtime, route_polyline)

__all__ = ["plot_routes", "plot_method_comparison", "plot_gap_to_reference",
           "plot_bnb_dual_gap", "plot_convergence", "plot_runtime",
           "route_polyline", "animate_routes"]
