from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core import database, security
from app.models import user as user_models
from app.api.v1.api import api_router
from app.services.discovery import discovery_service

app = FastAPI(title="LeafCloud Server V2 API")

@app.on_event("startup")
async def start_up_tasks():
    # Seed admin user
    seed_admin_user()
    
    # Start Zeroconf discovery
    await discovery_service.start(port=settings.PORT)

@app.on_event("shutdown")
async def shutdown_tasks():
    # Stop Zeroconf discovery
    await discovery_service.stop()

def seed_admin_user():
    db = database.SessionLocal()
    try:
        admin_email = settings.ADMIN_EMAIL
        admin_user = db.query(user_models.User).filter(user_models.User.email == admin_email).first()
        
        if not admin_user:
            print(f"Seeding admin user: {admin_email}")
            hashed_password = security.get_password_hash(settings.ADMIN_PASSWORD)
            new_admin = user_models.User(
                email=admin_email,
                name=settings.ADMIN_NAME,
                hashed_password=hashed_password,
                is_admin=True,
                is_verified=True
            )
            db.add(new_admin)
            db.commit()
            print("Admin user seeded successfully.")
        else:
            updated = False
            if not admin_user.is_admin:
                print(f"Updating existing seeded admin {admin_email} to is_admin=True")
                admin_user.is_admin = True
                updated = True
            if not admin_user.is_verified:
                print(f"Updating existing seeded admin {admin_email} to is_verified=True")
                admin_user.is_verified = True
                updated = True
            if updated:
                db.commit()
    except Exception as e:
        print(f"Error seeding admin user: {e}")
    finally:
        db.close()

app.mount("/images", StaticFiles(directory=settings.SOURCE_DIR), name="images")
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to LeafCloud Server V2 API"}
