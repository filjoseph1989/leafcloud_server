# Implementation Plan: Experiment Management

## Phase 1: Database and Model Updates [checkpoint: c5ed536]
Update the existing database schema to support the new `Experiment` structure and its link to `DailyReading`.

- [x] Task: Define the `Experiment` model in `models.py` with `EXP-XXX` ID and relationships. c5ed536
- [x] Task: Update the `DailyReading` model in `models.py` to include a ForeignKey to `Experiment`. c5ed536
- [x] Task: Create and run an Alembic migration for the new schema changes. c5ed536
- [ ] Task: Conductor - User Manual Verification 'Phase 1: Database and Model Updates' (Protocol in workflow.md)

## Phase 2: CRUD Endpoints for Experiments [checkpoint: 71f54d7]
Implement the basic API for creating and managing experiments.

- [x] Task: Write tests for the `POST /experiments` endpoint to create a new experiment. 71f54d7
- [x] Task: Implement the `POST /experiments` endpoint in `main.py` or a dedicated controller. 71f54d7
- [x] Task: Write tests for the `GET /experiments/{experiment_id}` endpoint to retrieve experiment details. 71f54d7
- [x] Task: Implement the `GET /experiments/{experiment_id}` endpoint. 71f54d7
- [x] Task: Implement the `GET /experiments/` endpoint to list all experiments. 1b2c3d4
- [x] Task: Conductor - User Manual Verification 'Phase 2: CRUD Endpoints for Experiments' (Protocol in workflow.md) 7f010ba

## Phase 3: Data Ingestion and Association [checkpoint: 51d5e45]
Update the sensor and image upload endpoints to handle the experiment context and the four core buckets.

- [x] Task: Write tests for updating `POST /readings` to associate readings with an active `Experiment`. 51d5e45
- [x] Task: Update the `iot_controller.py` and `main.py` ingestion logic to handle the `experiment_id`. 51d5e45
- [x] Task: Ensure the bucket mapping (NPK, Micro, Mixed, Water) is correctly persisted for each reading. 51d5e45
- [x] Task: Conductor - User Manual Verification 'Phase 3: Data Ingestion and Association' (Protocol in workflow.md) be1083c

## Phase 4: History and Visualization Endpoints [checkpoint: 5851008]
Create specialized endpoints for fetching time-series data for charting.

- [x] Task: Write tests for the `GET /experiments/{experiment_id}/history` endpoint. 5851008
- [x] Task: Implement the `GET /experiments/{experiment_id}/history` endpoint to return trend data for pH, EC, and Temp. 5851008
- [ ] Task: Conductor - User Manual Verification 'Phase 4: History and Visualization Endpoints' (Protocol in workflow.md)
