from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    qr_code = Column(String, nullable=True)
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class QRScan(Base):
    __tablename__ = "qr_scans"
    
    scan_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    arrival_time = Column(DateTime, default=datetime.utcnow)
    departure_time = Column(DateTime, nullable=True)
    matched = Column(Boolean, default=False)

class FaceRecognition(Base):
    __tablename__ = "face_recognition"
    
    reco_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    image_path = Column(String, nullable=False)
    face_matched = Column(Boolean, default=False)
    error_message = Column(String, nullable=True)

