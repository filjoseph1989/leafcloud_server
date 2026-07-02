from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Server Configuration
    PORT: int = 8000

    # Database Configuration
    DATABASE_URL: str = "sqlite:///./sql_app.db"
    DB_USER: str = "tin"
    DB_PASSWORD: str = ""
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "leafcloud"

    # Security & JWT
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Admin Initial Seeding
    ADMIN_EMAIL: str = "admin@leafcloud.com"
    ADMIN_NAME: str = "Super Admin"
    ADMIN_PASSWORD: str = "admin123"

    # Image Processing
    SOURCE_DIR: str = "images"
    OUTPUT_DIR: str = "cropped_dataset"
    CROP_SIZE: int = 224
    GREEN_THRESHOLD: float = 30.0
    AI_MODEL_PATH: str = "leafcloud_multimodal_v6_20260529_2001.keras"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
