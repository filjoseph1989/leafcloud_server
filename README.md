# LeafCloud Server V2

LeafCloud Server V2 is a robust, scalable backend built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy**. It features a secure JWT-based authentication system and automated network discovery using **Zeroconf (mDNS)**.

The project is architected following **SOLID principles** and modular layered patterns to ensure high maintainability and developer productivity.

## 🚀 Key Features

- **Modular Architecture**: Layered separation of concerns (Core, API, Models, Schemas, Services).
- **Secure Authentication**: JWT-based auth with Bcrypt password hashing.
- **Service Discovery**: Automatic mDNS broadcasting for easy local network discovery.
- **Database Migrations**: Systematic schema management using Alembic.
- **Environment Management**: Type-safe configuration via `pydantic-settings`.

---

## 🛠 Quick Start

### 1. Prerequisites
- Python 3.8+
- PostgreSQL
- A virtual environment (recommended)

### 2. Installation
```bash
git clone <repository-url>
cd mimeng_leafcloud_server_v2
pip install -r requirements.txt
```

### 3. Environment Setup
Copy the template and fill in your local database credentials:
```bash
cp .env.example .env
```

### 4. Database Migration
Update your PostgreSQL database to the latest schema:
```bash
export PYTHONPATH=$PYTHONPATH:.
alembic upgrade head
```

#### Common Migration Commands:
- **Apply migrations**: `export PYTHONPATH=$PYTHONPATH:. && alembic upgrade head`
- **Create new migration**: `export PYTHONPATH=$PYTHONPATH:. && alembic revision --autogenerate -m "description"`
- **Check current version**: `export PYTHONPATH=$PYTHONPATH:. && alembic current`
- **View history**: `export PYTHONPATH=$PYTHONPATH:. && alembic history`

### 5. Start the Server
```bash
uvicorn app.main:app --reload
```
The API will be available at `http://localhost:8000` and the interactive docs at `http://localhost:8000/docs`.

---

## 📖 Documentation Index

For detailed guides, please refer to our documentation pages:

1.  **[Authentication System](docs/page-1-login.md)** - Details on JWT and Login logic.
2.  **[Database Setup](docs/page-2-database-setup.md)** - Guide on PostgreSQL configuration.
3.  **[Migrations (Alembic)](docs/page-3-migrations-alembic.md)** - How to manage schema changes.
4.  **[Network Discovery](docs/page-4-zeroconf-discovery.md)** - Details on Zeroconf/mDNS implementation.
5.  **[Developer Guide](docs/page-5-developer-guide.md)** - **Start here** for architecture and contribution workflows.
6.  **[Daily Readings Model](docs/page-6-daily-readings.md)** - Details on the sensor data schema.
7.  **[Raw Daily Readings](docs/page-7-raw-daily-readings.md)** - Details on the raw sensor data collection.
8.  **[Experiments Model](docs/page-8-experiments.md)** - Details on the experimental configuration schema.
9.  **[Image Crops](docs/page-9-image-crops.md)** - Details on the segmented plant images used for AI.
10. **[NPK Predictions](docs/page-10-npk-predictions.md)** - Details on the numerical AI estimation outputs.
11. **[Image Crop Progress](docs/page-11-image-crop-progress.md)** - Task tracking for image processing.
12. **[Image Processing Logic](docs/page-12-image-processing-logic.md)** - Details on segmentation and greenness filtering.
13. **[Tank Configuration](docs/page-13-tank-configuration.md)** - Dynamic system settings and fertilizer profiles.
14. **[Mobile API Integration](docs/page-14-mobile-api-integration.md)** - How to connect your mobile app to the config API.
15. **[IoT Pi Integration](docs/page-15-iot-pi-integration.md)** - How to upload data from a Raspberry Pi.
16. **[Monitoring Dashboard](docs/page-16-dashboard-api.md)** - The data aggregation API for the farmer's UI.
17. **[Static Image Serving](docs/page-17-static-image-serving.md)** - How uploaded plant images are served statically.
18. **[History API](docs/page-18-history-api.md)** - Accessing historical sensor and reading data.
19. **[Alert Polling](docs/page-19-alert-polling.md)** - Real-time client polling for system status alerts.
20. **[Multi-task AI Model](docs/page-20-multi-task-ai-model.md)** - Deep learning architecture details for nutrient predictions.
21. **[Full-stack AI Integration](docs/page-21-full-stack-ai-integration.md)** - Pipeline integrating sensor reading and inference.
22. **[Message Definitions](docs/page-22-message-definitions.md)** - Dynamic alert and system notification definitions.
23. **[Sensor Calibration](docs/page-23-sensor-calibration.md)** - Device calibration settings and workflows.
24. **[EC Calibration Math](docs/page-23-ec-calibration-math.md)** - Underlying mathematical models for EC calibration.
25. **[Calibration API](docs/page-24-calibration-api.md)** - Endpoint schema and controllers for sensor calibration.
26. **[How Estimation Works](docs/page-25-how-estimation-works.md)** - Logic and algorithms behind soil/plant estimation.
27. **[Nutrient Classifier Training](docs/page-26-nutrient-classifier-training-summary.md)** - Training procedures and summary of the ML classifier.
28. **[Camera Streaming & Terminal Visualization](docs/page-27-camera-streaming.md)** - How to stream video and view it in a terminal or GUI.
29. **[Upload Interval Configuration](docs/page-28-upload-interval-configuration.md)** - Dynamic upload cooldown configuration and API schemas.
30. **[Dashboard Code Explanation](docs/page-29-dashboard-code-explanation.md)** - Line-by-line code explanation for the monitoring dashboard endpoint.
31. **[Model Evaluation (V3 vs V4)](docs/page-30-evaluation.md)** - Comparative analysis of V3 and V4 machine learning model performance.
32. **[Database Schema](docs/page-31-database-schema.md)** - Details on the tables, columns, and relationships in the PostgreSQL database.
33. **[Authentication Gaps](docs/page-32-auth-gaps.md)** - Analysis of missing authentication and authorization features in the current V2 server.
34. **[Role-Based Access Control (RBAC)](docs/page-33-rbac-implementation.md)** - Details on the implemented role-based authorization system.
35. **[Token Lifecycle Management](docs/page-34-token-lifecycle.md)** - Details on the access/refresh token dual lifecycle and logout blacklist.
36. **[Account Lifecycle Management](docs/page-35-account-lifecycle.md)** - Details on the account verification, password updates, and forgot/reset password flows.
37. **[Model V6 Evaluation & V7 Plan](docs/page-40-model-v6-evaluation-analysis.md)** - Detailed analysis of V6 performance under continuous targets and the V7 architecture plan.
38. **[Model V7 Evaluation & V8 Plan](docs/page-41-model-v7-evaluation-analysis.md)** - Detailed analysis of V7 performance under time targets, backpropagation leaks, and the V8 architecture plan.
39. **[Model V8 Evaluation & V9 Plan](docs/page-42-model-v8-evaluation-analysis.md)** - Detailed analysis of V8 performance under time targets, custom serialization, and the V9 architecture plan.
40. **[Model V9 Evaluation & V10 Plan](docs/page-43-model-v9-evaluation-analysis.md)** - Detailed analysis of V9 performance, shared feature contamination, and the V10 architecture plan.
41. **[Model V10 Evaluation & V11 Plan](docs/page-44-model-v10-evaluation-analysis.md)** - Detailed analysis of V10 performance, feature capacity bottleneck, and the V11 architecture plan.
42. **[Model V11 Evaluation](docs/page-44-model-v11-evaluation-analysis.md)** - Detailed analysis of V11 Independent Dual-Fusion performance.
43. **[Capstone Project Document Updates](docs/page-45-capstone-updates.md)** - Guidelines and tables to update the thesis document with V11 model results.
44. **[Model Evolution History (V1 to V11)](docs/page-47-model-evolution-history.md)** - Comprehensive history of the AI model design iterations, technical bottlenecks, and architectural resolutions.
45. **[Conceptual Framework Guide (V11)](docs/page-48-conceptual-framework-guide.md)** - Guide to update Section 3.2 (Conceptual Framework) of the Capstone thesis matching the V11 model's Input-Process-Output flow.
46. **[Manual Zeroconf Testing](docs/page-49-manual-zeroconf-testing.md)** - Reference guide for manually registering, browsing, and troubleshooting local mDNS service records using the `dns-sd` command-line tool.


---

## 🧪 Verification Tools

- **Verify Discovery**: `python scripts/verify-zeroconf.py`
- **Verify RBAC**: `python scripts/verify_rbac.py`
- **Verify Token Lifecycle**: `python scripts/verify_token_lifecycle.py`
- **Verify Account Lifecycle**: `python scripts/verify_account_lifecycle.py`
- **Process Images**: `python scripts/image_processor.py`
- **Seed Predictions**: `python scripts/seed_predictions.py`
- **Run SQL Queries**: `./scripts/run-query.sh "SELECT * FROM users;"`
