from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, func, CheckConstraint
from app.core.database import Base

class TankConfig(Base):
    __tablename__ = "tank_configs"

    id = Column(Integer, primary_key=True, index=True)
    tank_name = Column(String(50), nullable=False)
    water_volume_liters = Column(Float, nullable=False)
    
    # Macro Fertilizer Profile
    macro_brand_name = Column(String(100))
    macro_n_pct = Column(Float, nullable=False)
    macro_p_pct = Column(Float, nullable=False)
    macro_k_pct = Column(Float, nullable=False)
    macro_density = Column(Float, nullable=False, server_default="1.0", default=1.0)
    
    # Micro Fertilizer Profile
    micro_brand_name = Column(String(100))
    micro_n_pct = Column(Float, nullable=False)
    micro_p_pct = Column(Float, nullable=False)
    micro_k_pct = Column(Float, nullable=False)
    micro_density = Column(Float, nullable=False, server_default="1.0", default=1.0)
    
    # Target Recipe Dosages (mL/L)
    target_macro_dosage_mll = Column(Float, nullable=False)
    target_micro_dosage_mll = Column(Float, nullable=False) 
    
    upload_interval_seconds = Column(Integer, nullable=False, server_default="60")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint('macro_density > 0', name='macro_density_positive'),
        CheckConstraint('micro_density > 0', name='micro_density_positive'),
    )
