"""Instance generation, benchmark suites, and the on-disk formats."""
from drp.instances.generator import (BENCHMARK_SPECS, default_benchmark_suite,
                                     generate_instance, generate_zone_instance,
                                     zone_benchmark_suite)
from drp.instances.io import (INSTANCE_SCHEMA, SOLUTION_SCHEMA,
                              instance_from_dict, instance_to_dict,
                              load_instance, load_solution, save_instance,
                              save_solution, solution_from_dict,
                              solution_to_csv, solution_to_dict,
                              solution_to_geojson)

__all__ = [
    "generate_instance", "generate_zone_instance", "default_benchmark_suite",
    "zone_benchmark_suite", "BENCHMARK_SPECS",
    "INSTANCE_SCHEMA", "SOLUTION_SCHEMA",
    "instance_to_dict", "instance_from_dict", "save_instance", "load_instance",
    "solution_to_dict", "solution_from_dict", "save_solution", "load_solution",
    "solution_to_geojson", "solution_to_csv",
]
