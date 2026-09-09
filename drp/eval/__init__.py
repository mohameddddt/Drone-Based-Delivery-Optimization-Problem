"""Experiment running, the results store, and aggregation."""
from drp.eval.metrics import best_known, instance_rows, method_summary
from drp.eval.runner import METHODS, MethodResult, run_study, solve_one
from drp.eval.stats import (FriedmanResult, SignificanceReport, WilcoxonResult,
                            bootstrap_ci, friedman_test,
                            nemenyi_critical_difference, significance_report,
                            wilcoxon_pairwise)
from drp.eval.store import ResultStore, RunRecord, git_sha

__all__ = ["ResultStore", "RunRecord", "git_sha", "solve_one", "run_study",
           "MethodResult", "METHODS", "instance_rows", "method_summary",
           "best_known", "significance_report", "SignificanceReport",
           "wilcoxon_pairwise", "WilcoxonResult", "friedman_test",
           "FriedmanResult", "nemenyi_critical_difference", "bootstrap_ci"]
