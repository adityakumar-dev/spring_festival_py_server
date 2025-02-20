from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship, backref
from datetime import datetime
from database import Base

class Institution(Base):
    __tablename__ = "institutions"
    
    institution_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # One-to-many relationship with users
    users = relationship("User", back_populates="institution")

class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    aadhar_number = Column(String, unique=True, nullable=True)
    image_path = Column(String)
    qr_code = Column(String, nullable=True)
    is_student = Column(Boolean, default=False)
    is_instructor = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    institution_id = Column(Integer, ForeignKey("institutions.institution_id"), nullable=True)
    # instructor_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    # instructor_group_id = Column(Integer, ForeignKey("instructor_groups.instructor_group_id"), nullable=True)
    
    # Relationships
    institution = relationship("Institution", back_populates="users")
    # instructor_group = relationship("InstructorGroup", back_populates="instructors")
    
    # Self-referential relationship for instructor-student
    # students = relationship(
    #     "User",
    #     "Institution"
    #     # backref=backref("instructor", remote_side=[user_id]),
    #     # foreign_keys=[instructor_id]
    # )
    
    # One-to-many relationships
    qr_scans = relationship("QRScan", back_populates="user")
    face_recognitions = relationship("FaceRecognition", back_populates="user")

class QRScan(Base):
    __tablename__ = "qr_scans"
    
    scan_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    arrival_time = Column(DateTime, default=datetime.utcnow)
    departure_time = Column(DateTime, nullable=True)
    is_bypass = Column(Boolean, default=False)
    bypass_reason = Column(String, nullable=True)
    matched = Column(Boolean, default=False)

    # Many-to-one relationship with user
    user = relationship("User", back_populates="qr_scans")

class FaceRecognition(Base):
    __tablename__ = "face_recognitions"
    
    recognition_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    image_path = Column(String)
    face_matched = Column(Boolean)
    error_message = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Many-to-one relationship with user
    user = relationship("User", back_populates="face_recognitions")

class QuickRegister(Base):
    __tablename__ = "quick_registers"
    
    register_id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    aadhar_number = Column(String, unique=True, nullable=True)
    image_path = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
