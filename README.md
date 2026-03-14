# LEAFCLOUD Server

Production Backend for the LEAFCLOUD Hydroponic Monitoring System. This API handles sensor data persistence, AI-driven growth recommendations, and live video streaming proxies.

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.12+**
- **PostgreSQL** (running and accessible)
- **OpenCV Dependencies** (System-level libraries for image processing)

### 2. Installation

Clone the repository and set up the virtual environment:

```bash
# Create virtual environment (if not using the pre-configured one)
python -m venv ~/.env_leafcloud
source ~/.env_leafcloud/bin/activate

# Install dependencies
pip install -r requirements.text
```

### 3. Configuration

Create a `.env` file in the root directory:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/leafcloud

# Optional: Individual DB params (fallback)
DB_USER=user
DB_PASSWORD=password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=leafcloud

# Video Stream Source
VIDEO_STREAM_URL=udp://0.0.0.0:5000
```

### 4. Database Setup

Ensure your PostgreSQL database is running, then apply migrations:

```bash
# Apply migrations to bring DB to latest schema
alembic upgrade head

# (Optional) Seed initial data for testing
python seed_data.py
```

### 5. Running the App

Start the FastAPI server using Uvicorn:

```bash
# Using the python runner directly
python main.py

# OR using uvicorn CLI
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.
You can access the interactive documentation at `http://localhost:8000/docs`.

---

## 🧪 Testing

The project uses `pytest` for unit and integration testing.

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=main --cov=models
```

---

## 🛰️ Core Endpoints

### IOT Integration
- `POST /iot/sensor_data/`: Receive JSON payloads (temp, ph, ec) from Raspberry Pi.
- `POST /iot/upload_data/`: Upload images and form data for AI analysis.
- `GET /video_feed`: MJPEG proxy for live camera feed.

### Application API
- `POST /login`: Admin authentication.
- `GET /app/latest_status`: Get the most recent sensor readings and AI recommendations.
- `GET /app/history`: Retrieve historical data for analytics.

---

## 🧠 AI Features
The server includes a MobileNetV2-based brain that classifies lettuce growth stages and provides recommendations. If the model file (`leafcloud_mobilenetv2_model.h5`) is missing, the server will fall back to dummy predictions for development.

```sql
pg_dump -U fil leafcloud > leafcloud_backup_$(date +%Y%m%d_%H%M%S).sql 
```