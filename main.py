import os
from fastapi import FastAPI, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models
import shutil
from uuid import uuid4
from qr_generation import generate_qr_code, generate_qr_codes
from face_auth import is_face_match
from fastapi import HTTPException
import base64

app = FastAPI()

# Create Tables
models.Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create a User@app.post("/create_user")
@app.post("/create_user")
def create_user(
    name: str = Form(...),  # Ensure it's part of multipart/form-data
    email: str = Form(...),  # Ensure it's part of multipart/form-data
    image: UploadFile = File(...),  
    db: Session = Depends(get_db)
):
    # Check if user exists
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        return {"error": "User already exists"}

    print(f"Creating user: {name}, {email}")

    # Save uploaded image
    image_filename = f"{uuid4().hex}_{image.filename}"
    image_path = os.path.join(UPLOAD_DIR, image_filename)
    
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # Create new user
    new_user = models.User(name=name, email=email, image_path=image_path)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate QR Code and update user
    qr_path = generate_qr_code(new_user.user_id, new_user.name, new_user.email)
    new_user.qr_code = qr_path
    db.commit()

    return {
        "user_id": new_user.user_id, 
        "name": new_user.name, 
        "qr_code": new_user.qr_code, 
        "image_path": new_user.image_path
    }

# Get QR Code Image
@app.get("/qr_code/{user_id}")
def get_qr_code(user_id: int):
    qr_path = f"qrs/qr_code_{user_id}.png"

    if not os.path.exists(qr_path):
        return {"error": "QR code not found"}

    return FileResponse(qr_path, media_type="image/png")

@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    # users = db.query(models.User).all()
    # face_recognition = db.query(models.FaceRecognition).all()
    # qr_code = db.query(models.QRScan).all()
    # return {'name': users.name, 'email': users.email, 'image_path': users.image_path, 'qr_code': qr_code, 'face_recognition': face_recognition}
    return db.query(models.User).all()


# Get User by ID
@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if user is None:
            return {"error": "User not found"}

        # Get verification records
        face_recognition = db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()
        qr_scan = db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()

        # Initialize response data
        response_data = {
            "user": {
                "user_id": user.user_id,
                "name": user.name,
                "email": user.email,
                "image_path": user.image_path,
                "qr_code_path": user.qr_code
            },
            "face_recognition": face_recognition,
            "qr_scan": qr_scan,
            "image_base64": None,
            "qr_base64": None
        }

        # Add base64 encoded image if exists
        if user.image_path and os.path.exists(user.image_path):
            with open(user.image_path, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode()
                response_data["image_base64"] = f"data:image/jpeg;base64,{img_data}"

        # Add base64 encoded QR code if exists
        if user.qr_code and os.path.exists(user.qr_code):
            with open(user.qr_code, "rb") as qr_file:
                qr_data = base64.b64encode(qr_file.read()).decode()
                response_data["qr_base64"] = f"data:image/png;base64,{qr_data}"

        return JSONResponse(content=response_data)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

# Scan QR Code (Insert Entry)
@app.post("/qr_scans/verify")
def scan_qr(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if user is None:
            return {"error": "User not found"}
        
        # Check if user already has an arrival time for today
        from datetime import datetime
        today = datetime.now().date()
        existing_scan = db.query(models.QRScan).filter(
            models.QRScan.user_id == user_id,
            db.func.date(models.QRScan.arrival_time) == today
        ).first()
        
        if existing_scan:
            return {"error": "User already checked in today"}
        
        # Create new scan entry
        scan = models.QRScan(user_id=user_id)
        db.add(scan)
        db.commit()
        
        # Return before refresh to avoid potential issues
        return {
            "message": "Check-in successful",
            "user_id": user_id,
            "arrival_time": scan.arrival_time
        }
    except Exception as e:
        db.rollback()  # Rollback any failed transaction
        print(f"Error in scan_qr: {str(e)}")  # Log the error
        return {"error": f"Internal server error: {str(e)}"}

# Get QR Scan History
@app.get("/qr_scans/{user_id}")
def get_qr_history(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()

# Face Recognition Log
@app.post("/face_recognition/")
def log_face_recognition(user_id: int, image_path: str, face_matched: bool, db: Session = Depends(get_db)):
    reco = models.FaceRecognition(user_id=user_id, image_path=image_path, face_matched=face_matched)
    db.add(reco)
    db.commit()
    db.refresh(reco)
    return reco

# Get Face Recognition History
@app.get("/face_recognition/{user_id}")
def get_face_recognition_history(user_id: int, db: Session = Depends(get_db)):
    return db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()

@app.get('/user/image/{user_id}')
def get_user_image(user_id: int, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user.image_path or not os.path.exists(user.image_path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        return FileResponse(
            user.image_path,
            media_type="image/jpeg",  # Adjust media type based on your image format
            filename=f"user_{user_id}_image.jpg"  # Name of the file when downloaded
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/face_recognition/verify")
async def verify_face(
    user_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        print(f"Processing request for user_id: {user_id}")
        user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user:
            return {"error": "User not found"}
        
        print(f"Found user with image_path: {user.image_path}")
        stored_image_path = user.image_path
        
        if not stored_image_path or not os.path.exists(stored_image_path):
            print(f"Stored image not found at path: {stored_image_path}")
            return {"error": "Stored image not found"}
        
        temp_image_path = os.path.join(UPLOAD_DIR, f"temp_{uuid4().hex}_{image.filename}")
        try:
            print(f"Saving temporary image to: {temp_image_path}")
            await image.seek(0)
            
            with open(temp_image_path, "wb") as buffer:
                content = await image.read()
                buffer.write(content)
            
            print("Calling face_match function")
            is_match = is_face_match(stored_image_path, temp_image_path)
            # Convert numpy.bool_ to Python bool
            is_match = bool(is_match)
            print(f"Face match result: {is_match}")
            return {"is_match": is_match}
        
        finally:
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
                print("Temporary file removed")
                
    except Exception as e:
        print(f"Error in verify_face: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {"error": f"Internal server error: {str(e)}"}
   