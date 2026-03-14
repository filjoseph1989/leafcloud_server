# Tech Stack: LEAFCLOUD API

## Backend Infrastructure
- **Programming Language:** Python
- **API Framework:** FastAPI
- **Asynchronous Server:** Uvicorn
- **Object-Relational Mapper (ORM):** SQLAlchemy
- **Schema Migrations:** Alembic
- **Validation & Serialization:** Pydantic

## Data & Storage
- **Primary Database:** PostgreSQL (psycopg2-binary)
- **Local Storage:** Filesystem for static images and AI model binaries.

## Machine Learning & Computer Vision
- **Framework:** TensorFlow / Keras (using MobileNetV2 for NPK prediction)
- **Image Processing:** OpenCV (cv2), Pillow (PIL)
- **Numerical Computation:** NumPy, Pandas

## Testing & Quality Assurance
- **Test Runner:** pytest
- **Mocking:** pytest-mock
- **HTTP Client (Testing):** TestClient (httpx)

## Utilities
- **HTTP Client:** Requests
- **Environment Management:** python-dotenv
