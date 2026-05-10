# Drone Delivery Data Builder

This project includes a reproducible data generator for the drone delivery routing problem. The original coordinates file is never modified; each data build is saved into a new run folder with a full config snapshot.

## What the notebook does

The notebook defines functions to:
- Load and standardize the base coordinates
- Split the data into fixed instances
- Choose a depot location
- Assign customer demands
- Optionally add no-fly zones
- Save each instance to its own folder

## Files and folders

- Last_Mile_Delivery_Coordinates.csv: Base coordinates (read-only input)
- data_instance_builder.ipynb: Notebook that generates instances
- data_generated/: Output root for all generated runs

## Output structure

Each run creates a folder like:

  data_generated/run_YYYYMMDD_HHMMSS/
    config.json
    instance_01/
      customers.csv
      distance_km.csv
      meta.json
    instance_02/
      customers.csv
      distance_km.csv
      meta.json
    ...

## Defaults (change any time)

Defaults are set in InstanceConfig inside the notebook:
- 10 instances
- Depot = centroid of each instance
- Drones = proportional to customers (min 3)
- Demand = seeded random (reproducible)
- No-fly zones = off by default

## How to generate data

1) Open data_instance_builder.ipynb
2) Run the cells from top to bottom
3) Adjust InstanceConfig values as needed
4) Run the generation cell to create a new run folder

Each run is stored in a new timestamped folder so no previous data is overwritten.
