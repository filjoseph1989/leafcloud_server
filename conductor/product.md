# Initial Concept\nProduction Backend for LEAFCLOUD System

# Product Guide: LEAFCLOUD API

## Project Overview
LEAFCLOUD API is a production-grade backend for the LEAFCLOUD system, designed to integrate IoT sensor data, computer vision AI, and a mobile application dashboard. It facilitates automated nutrient monitoring and actionable recommendations for agricultural systems, specifically focusing on lettuce growth.

## Target Users
- **System Administrators:** Overseeing the backend and data integrity.
- **IoT Device (Raspberry Pi):** Automated data uploader for batched sensor readings and plant images.
- **Mobile App Users (Android):** Growers monitoring their system and receiving automated recommendations.

## Core Features
- **IoT Data Integration:** Endpoint for uploading batched sensor data (pH, EC, Water Temperature) and plant images, with support for centralized logging.
- **Data Correction API:** Manual pH override endpoint to correct estimated values from IoT devices with high-precision measurements, following a FIFO logic per experiment.
- **Experiment Management:** Organize data into specific crop cycles (e.g., "Lettuce Batch Oct 2026") using standard `EXP-XXX` identifiers, with data grouped by functional buckets (NPK, Micro, Mixed, Water). Includes server-side auto-initialization of experiments for zero-config IoT data ingestion.
- **Bucket Control System:** Manage and track active nutrient buckets (NPK, Micro, Mix, Water) for precise sensor data attribution.
- **AI-Driven Prediction:** Automated NPK (Nitrogen, Phosphorus, Potassium) levels estimation from image data using a MobileNetV2-based model.
- **Remote IoT Control:** Endpoint for the mobile app to remotely restart the IoT device script and reset the server's video feed to clear stale frames.
- **Administrative Data Management:** Endpoints for browsing, synchronizing, and deleting captured images and associated sensor data. Includes **automated pre-filtering** to remove metadata, corrupted captures, and images with low "greenness", and a **trash recovery system** to browse, track, and undo these automated actions via the UI.
- **Actionable Recommendations:** Rule-based engine providing advice based on NPK, pH, and EC readings.
- **Historical Monitoring:** Endpoints for fetching historical data for visualization and charts, including AI-generated NPK predictions and image URLs.
- **Alert System:** Proactive notifications for critical system conditions (pH lockout, nutrient burn, deficiencies).
- **Mobile API:** Specialized endpoints for dashboard status and alerts.

## Technical Architecture
- **Backend:** FastAPI for high-performance, asynchronous endpoints.
- **Database:** PostgreSQL managed via SQLAlchemy ORM and Alembic migrations.
- **AI:** Keras/TensorFlow model integration for real-time plant health analysis.
- **Static Assets:** Local image storage and serving for visual monitoring.
