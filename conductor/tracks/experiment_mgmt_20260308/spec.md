# Specification: Experiment Management for LEAFCLOUD API

## 1. Overview
The Experiment Management feature allows users to organize and monitor lettuce growth experiments. It introduces a structured way to track sensor data and plant images within specific "Experiments," moving beyond a simple flat list of readings. This feature will focus on managing the four primary buckets (NPK, Micro, Mixed, Water) and providing historical data visualization.

## 2. Functional Requirements
- **Experiment Lifecycle:**
  - Create a new experiment with a unique identifier (Standard prefix `EXP-XXX`).
  - List all existing experiments.
  - Link each experiment to a fixed set of four functional buckets: **NPK**, **Micro**, **Mixed**, and **Water**.
- **Data Collection:**
  - Record and store `pH`, `EC`, and `Water Temperature` readings for each experiment.
  - Link captured plant images to the specific experiment and bucket context.
- **Data Visualization:**
  - Provide an endpoint to fetch historical data for an experiment.
  - The primary visualization for history will be **Graphical Trends (Charts)**, showing how pH, EC, and Temperature change over time.
- **Bucket Control:**
  - Support the "Bucket Control System" defined in the Product Definition to manage which bucket is currently active for sensing or dosing.

## 3. Non-Functional Requirements
- **Scalability:** The database schema must handle many experiments and thousands of daily readings efficiently.
- **Performance:** History endpoints should return data quickly enough for interactive charting on the mobile dashboard.

## 4. Acceptance Criteria
- Users can create a new experiment through a REST API endpoint.
- All new sensor readings and images can be associated with an active experiment.
- A dedicated endpoint returns a time-series dataset of `pH`, `EC`, and `Temp` for a given Experiment ID, suitable for charting.
- The system correctly handles the mapping of the four core buckets (NPK, Micro, Mixed, Water) within the experiment context.

## 5. Out of Scope
- Dynamic creation of custom bucket labels (limited to the four core buckets for now).
- Ambient humidity and temperature sensing (future enhancement).
- Water level sensing (future enhancement).
