"""Instance generation, benchmark suites, real geography, and the on-disk formats."""
from drp.instances.benchmarks import (ImportedInstance, read_benchmark,
                                      read_benchmark_suite, read_cvrplib,
                                      read_solomon)
from drp.instances.generator import (BENCHMARK_SPECS, calibrate_battery,
                                     default_benchmark_suite,
                                     generate_instance, generate_zone_instance,
                                     zone_benchmark_suite)
from drp.instances.geodata import (DEFAULT_DATASET, GEO_BENCHMARK_SPECS,
                                   DeliveryPoint, build_geo_instance,
                                   district_centroids, filter_points,
                                   geo_benchmark_suite, geo_circle_polygon,
                                   instance_from_points, load_delivery_points,
                                   sample_points)
from drp.instances.io import (INSTANCE_SCHEMA, SOLUTION_SCHEMA,
                              instance_from_dict, instance_to_dict,
                              load_instance, load_solution, save_instance,
                              save_solution, solution_from_dict,
                              solution_to_csv, solution_to_dict,
                              solution_to_geojson)
from drp.instances.qgc import (Anchor, mission_summary, route_to_qgc_plan,
                               solution_to_qgc_plans, write_qgc_plans)
from drp.instances.scenario import (SCENARIO_SCHEMA, build_scenario,
                                    build_scenario_file, load_scenario,
                                    save_scenario, scenario_template)

__all__ = [
    # generation
    "generate_instance", "generate_zone_instance", "default_benchmark_suite",
    "zone_benchmark_suite", "BENCHMARK_SPECS", "calibrate_battery",
    # real geography (§3.2)
    "DEFAULT_DATASET", "DeliveryPoint", "load_delivery_points",
    "filter_points", "sample_points", "district_centroids",
    "geo_circle_polygon", "instance_from_points", "build_geo_instance",
    "geo_benchmark_suite", "GEO_BENCHMARK_SPECS",
    # scenarios (§3.1)
    "SCENARIO_SCHEMA", "scenario_template", "load_scenario", "save_scenario",
    "build_scenario", "build_scenario_file",
    # benchmark import (§3.3)
    "ImportedInstance", "read_cvrplib", "read_solomon", "read_benchmark",
    "read_benchmark_suite",
    # formats
    "INSTANCE_SCHEMA", "SOLUTION_SCHEMA",
    "instance_to_dict", "instance_from_dict", "save_instance", "load_instance",
    "solution_to_dict", "solution_from_dict", "save_solution", "load_solution",
    "solution_to_geojson", "solution_to_csv",
    # flight-plan export (§3.5)
    "Anchor", "route_to_qgc_plan", "solution_to_qgc_plans", "write_qgc_plans",
    "mission_summary",
]
