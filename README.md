# Drone-Based Delivery Optimization

This project solves a capacitated drone delivery routing problem with battery limits and payload-dependent energy consumption. It includes two mathematical formulations in the report, an exact branch-and-bound method, a genetic algorithm, simulated annealing, generated benchmark instances, and experimental results.

## Structure

- `drone_delivery/`: Python package with the data model, solver methods, benchmark generator, and CLI
- `data/instances/`: 10 feasible benchmark instances used in the experiments
- `data/source/`: original coordinate source file
- `data/legacy_generated/`: preserved starter generated data
- `notebooks/`: preserved starter notebook
- `results/`: experiment tables and route solutions
- `report/report.tex`: final written report source

## Run

The project uses only the Python standard library.

Generate the benchmark:

```bash
python -m drone_delivery.cli generate --output data/instances --count 10 --seed 2026
```

Run the full experiment:

```bash
python -m drone_delivery.cli experiment --instances data/instances --output results --seed 2026 --time-limit 60
```

Solve one instance with all methods:

```bash
python -m drone_delivery.cli solve data/instances/instance_10 --method all --output results/demo
```

## Methods

The exact method enumerates feasible routes, keeps the cheapest route for each customer subset, and solves the resulting set-partitioning model with branch and bound.

The genetic algorithm uses a giant-tour encoding, ordered crossover, tournament selection, elitism, and swap/reverse/insert mutation. Simulated annealing uses the same encoding and neighborhood moves with exponential cooling.

Both metaheuristics use a dynamic split decoder that repairs a customer permutation into feasible drone routes under payload and battery constraints.

## Current Results

The latest run is stored in `results/experiment_results.csv` and `results/summary.csv`. Branch and bound solved all 10 benchmark instances to proven optimality. The average gaps were 0.0599 percent for the genetic algorithm and 0.0525 percent for simulated annealing.
