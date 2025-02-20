import os
from fastapi import FastAPI, Depends, UploadFile, File, Form, Query
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
from fastapi.middleware.cors import CORSMiddleware
import traceback

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

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
@app.get("/health-check")
async def health_check():
    return {"status": "ok"}

@app.post("/check/aadhar")
async def check_aadhar(aadhar_number: str = Form(...), db: Session = Depends(get_db)):
    try:
        if not aadhar_number or not aadhar_number.strip():
            raise HTTPException(status_code=400, detail="Aadhar number is required")
            
        user = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
        return {"exists": bool(user)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking Aadhar number: {str(e)}")

@app.post("/check/email/{email}")
def check_email(email: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        return {"exists": True}
    else:
        return {"exists": False}
    
# Create a User@app.post("/create_user")
@app.post("/create_user")
def create_user(
    name: str = Form(...),
    email: str = Form(...),
    aadhar_number: str = Form(None),
    image: UploadFile = File(...),
    user_type: str = Form(...),  # "individual", "instructor", or "student"
    institution_id: int = Form(None) ,  # Required for instructor
    # instructor_id: int = Form(None),  # Required for student
    db: Session = Depends(get_db)
):
    try:
        # Check if user exists
        existing_user = db.query(models.User).filter(models.User.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="User already exists")

        # Check if Aadhar number already exists (if provided)
        if aadhar_number:
            existing_aadhar = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
            if existing_aadhar:
                raise HTTPException(status_code=400, detail="Aadhar number already registered")

        # Validate institution for instructor
        if user_type == "instructor":
            if not institution_id:
                raise HTTPException(status_code=400, detail="Institution ID is required for instructor registration")
            institution = db.query(models.Institution).filter(
                models.Institution.institution_id == institution_id
            ).first()
            if not institution:
                raise HTTPException(status_code=404, detail="Institution not found")

        # Save uploaded image
        image_filename = f"{uuid4().hex}_{image.filename}"
        image_path = os.path.join(UPLOAD_DIR, image_filename)
        
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)

        # Handle instructor_id assignment
        # Convert UUID to string
        # For students, use the provided instructor_id
        # For individual users, it remains None
        
        # Create new user
        new_user = models.User(
            name=name,
            email=email,
            aadhar_number=aadhar_number,
            image_path=image_path,
            is_student=(user_type == "student"),
            is_instructor=(user_type == "instructor"),
            institution_id=institution_id,
            # instructor_id=instructor_id
        )
        
        db.add(new_user)
        db.flush()

        # Generate QR Code
        qr_path = generate_qr_code(new_user.user_id, new_user.name, new_user.email)
        new_user.qr_code = qr_path
        
        db.commit()
        db.refresh(new_user)

        return {
            "user_id": new_user.user_id,
            "name": new_user.name,
            "email": new_user.email,
            "aadhar_number": new_user.aadhar_number,
            "qr_code": new_user.qr_code,
            "image_path": new_user.image_path,
            "is_student": new_user.is_student,
            "is_instructor": new_user.is_instructor,
            "institution_id": new_user.institution_id,
            # "instructor_id": new_user.instructor_id
        }

    except Exception as e:
        print(f"Error creating user: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating user: {str(e)}")

# Get QR Code Image
@app.get("/qr_code/{user_id}")
def get_qr_code(user_id: int):
    qr_path = f"qrs/qr_code_{user_id}.png"

    if not os.path.exists(qr_path):
        return {"error": "QR code not found"}

    return FileResponse(qr_path, media_type="image/png")

@app.get("/users/")
def get_users(
    user_type: str = Query(None),  # "all", "individual", "instructor", "student", "quick"
    institution_id: int = Query(None),
    # instructor_id: int = Query(None),
    db: Session = Depends(get_db)
):
    result = []
    
    # Get regular users
    query = db.query(models.User)
    
    if user_type == "instructor":
        query = query.filter(models.User.is_instructor.is_(True))
    elif user_type == "student":
        query = query.filter(models.User.is_student.is_(True))
    
    if institution_id:
        query = query.filter(models.User.institution_id == institution_id)
    # if instructor_id:
    #     query = query.filter(models.User.instructor_id == instructor_id)
    
    users = query.all()
    for user in users:
        result.append({
            "id": user.user_id,
            "name": user.name,
            "email": user.email,
            "aadhar_number": user.aadhar_number,
            "image_path": user.image_path,
            "created_at": user.created_at,
            "is_quick_register": False,
            **{k: getattr(user, k) for k in ["is_student", "is_instructor", "institution_id"]}
        })

    # Get quick register users if type is "all" or "quick"
    if user_type in [None, "all", "quick"]:
        quick_users = db.query(models.QuickRegister).all()
        for quick_user in quick_users:
            result.append({
                "id": quick_user.register_id,
                "name": quick_user.name,
                "email": quick_user.email,
                "aadhar_number": quick_user.aadhar_number,
                "image_path": quick_user.image_path,
                "created_at": quick_user.created_at,
                "is_quick_register": True,
                "is_student": False,
                "is_instructor": False,
                "institution_id": None,
            })
    
    return result
@app.post("/institutions/")
def add_institutions(
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if institution already exists
    existing_institution = db.query(models.Institution).filter(models.Institution.name == name).first()
    if existing_institution:
        raise HTTPException(status_code=400, detail="Institution already exists")

    # Add new institution
    new_institution = models.Institution(name=name)
    db.add(new_institution)
    db.commit()
    db.refresh(new_institution)
    
    return {"message": "Institution added successfully", "institution": new_institution}

@app.get("/institutions/")
def get_institutions(db: Session = Depends(get_db)):
    return db.query(models.Institution).all()

@app.get("/institution/{institution_id}/instructors")
def get_institution_instructors(
    institution_id: int,
    db: Session = Depends(get_db)
):
    instructors = db.query(models.User).filter(
        models.User.institution_id == institution_id,
        models.User.is_instructor.is_(True)
    ).all()
    return instructors

@app.get("/instructor/{instructor_group_id}/students")
def get_instructor_students(
    instructor_group_id: str,
    db: Session = Depends(get_db)
):
    students = db.query(models.User)\
        .filter(
            models.User.instructor_group_id == instructor_group_id,
            models.User.is_instructor.is_(False)
        )\
        .all()
    return students

# QR Code scanning route
@app.post("/scan_qr")
def scan_qr(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create new QR scan record
    new_scan = models.QRScan(user_id=user.user_id)
    db.add(new_scan)
    db.commit()
    
    return {
        "scan_id": new_scan.scan_id,
        "user": {
            "name": user.name,
            "email": user.email,
            "is_instructor": user.is_instructor,
            "institution": user.institution
        },
        "timestamp": new_scan.arrival_time
    }

# Face Recognition route
@app.post("/verify_face")
async def verify_face(
    user_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Save the uploaded verification image
    verify_image_filename = f"verify_{uuid4().hex}_{image.filename}"
    verify_image_path = os.path.join(UPLOAD_DIR, verify_image_filename)
    
    with open(verify_image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # Perform face verification (implement your face recognition logic here)
    face_matched = True  # Replace with actual face verification logic
    
    # Record the face recognition attempt
    recognition = models.FaceRecognition(
        user_id=user.user_id,
        image_path=verify_image_path,
        face_matched=face_matched
    )
    db.add(recognition)
    db.commit()

    return {
        "user_id": user.user_id,
        "face_matched": face_matched,
        "institution": user.institution,
        "is_instructor": user.is_instructor
    }

# Update user route
@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    name: str = Form(None),
    email: str = Form(None),
    aadhar_number: str = Form(None),  # New parameter
    institution_id: int = Form(None),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Debug: Print incoming data
    print(f"Received update request for user {user_id}")
    # print(f"Name: {name}, Email: {email}, Institution: {institution_id})

    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Debug: Print user before update
    print(f"Before update - User data: {user.__dict__}")

    # Track if any changes were made
    changes_made = False

    # Update basic fields if provided
    if name is not None and name.strip():  # Check if name is not None and not empty
        user.name = name
        changes_made = True
        print(f"Updating name to: {name}")

    if email is not None and email.strip():  # Check if email is not None and not empty
        existing_user = db.query(models.User).filter(
            models.User.email == email,
            models.User.user_id != user_id
        ).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = email
        changes_made = True
        print(f"Updating email to: {email}")

    if institution_id is not None and institution_id.strip():
        user.institution_id = institution_id
        changes_made = True
        print(f"Updating institution_id to: {institution_id}")

    # if instructor_id is not None and instructor_id.strip():
    #     user.instructor_id = instructor_id
    #     changes_made = True
    #     print(f"Updating instructor_id to: {instructor_id}")

    if aadhar_number is not None and aadhar_number.strip():
        existing_aadhar = db.query(models.User).filter(
            models.User.aadhar_number == aadhar_number,
            models.User.user_id != user_id
        ).first()
        if existing_aadhar:
            raise HTTPException(status_code=400, detail="Aadhar number already exists")
        user.aadhar_number = aadhar_number
        changes_made = True
        print(f"Updating aadhar_number to: {aadhar_number}")

    if image:
        # Handle image update
        if user.image_path and os.path.exists(user.image_path):
            try:
                os.remove(user.image_path)
            except Exception as e:
                print(f"Error deleting old image: {e}")

        image_filename = f"{uuid4().hex}_{image.filename}"
        image_path = os.path.join(UPLOAD_DIR, image_filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        user.image_path = image_path
        changes_made = True
        print(f"Updating image path to: {image_path}")

    try:
        if not changes_made:
            print("No changes were made to update")
            return {"message": "No changes provided for update"}

        print("Committing changes to database...")
        db.commit()
        db.refresh(user)

        # Debug: Print user after update
        print(f"After update - User data: {user.__dict__}")

        return {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "aadhar_number": user.aadhar_number,
            "image_path": user.image_path,
            "is_instructor": user.is_instructor,
            "institution_id": user.institution_id,
            # "instructor_id": user.instructor_id,
            "qr_code": user.qr_code
        }
    except Exception as e:
        print(f"Error during update: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating user: {str(e)}")

# Delete user route
@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete associated records
    db.query(models.QRScan).filter(models.QRScan.user_id == user_id).delete()
    db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).delete()
    
    # Delete user
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}
@app.get("/users/{user_id}")
def get_user(
    user_id: int, 
    is_quick_register: bool = Query(False),
    db: Session = Depends(get_db)
):
    try:
        print(f"Fetching user with ID: {user_id}, is_quick_register: {is_quick_register}")  # Debug log

        if not is_quick_register:
            # Check regular users
            user = db.query(models.User).filter(models.User.user_id == user_id).first()
            if user:
                response_data = {
                    "user": {
                        "user_id": user.user_id,
                        "name": user.name,
                        "email": user.email,
                        "is_instructor": user.is_instructor,
                        "institution": user.institution.name if user.institution else None,
                        "image_path": f"/user/image/{user.user_id}?is_quick_register=false",
                        "qr_code_path": f"/qr_code/{user.user_id}",
                        "qr_code": user.qr_code,
                        "is_quick_register": False
                    },
                    "face_recognition": [
                        {
                            "recognition_id": fr.recognition_id,
                            "timestamp": fr.timestamp,
                            "face_matched": fr.face_matched
                        } for fr in db.query(models.FaceRecognition).filter(models.FaceRecognition.user_id == user_id).all()
                    ],
                    "qr_scan": [
                        {
                            "scan_id": qs.scan_id,
                            "arrival_time": qs.arrival_time
                        } for qs in db.query(models.QRScan).filter(models.QRScan.user_id == user_id).all()
                    ],
                    "image_base64": None,
                    "qr_base64": None
                }

                # Add QR code base64 if exists
                try:
                    if user.qr_code and os.path.exists(user.qr_code):
                        with open(user.qr_code, "rb") as qr_file:
                            qr_data = base64.b64encode(qr_file.read()).decode()
                            response_data["qr_base64"] = f"data:image/png;base64,{qr_data}"
                except Exception as qr_error:
                    print(f"Error processing QR code: {str(qr_error)}")
                    response_data["qr_base64"] = None

            else:
                raise HTTPException(status_code=404, detail="Regular user not found")
        else:
            print(f"Querying QuickRegister table for ID: {user_id}")  # Debug log
            # Check quick register users
            quick_user = db.query(models.QuickRegister).filter(models.QuickRegister.register_id == user_id).first()
            if quick_user:
                print(f"Found quick user: {quick_user.name}")  # Debug log
                response_data = {
                    "user": {
                        "user_id": quick_user.register_id,
                        "name": quick_user.name,
                        "email": quick_user.email,
                        "image_path": f"/user/image/{quick_user.register_id}?is_quick_register=true",
                        "is_quick_register": True,
                        "created_at": str(quick_user.created_at)
                    },
                    "image_base64": None
                }
            else:
                raise HTTPException(status_code=404, detail="Quick register user not found")

        # Add base64 encoded image if exists
        try:
            image_path = user.image_path if not is_quick_register else quick_user.image_path
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as img_file:
                    img_data = base64.b64encode(img_file.read()).decode()
                    response_data["image_base64"] = f"data:image/jpeg;base64,{img_data}"
        except Exception as img_error:
            print(f"Error processing image: {str(img_error)}")
            response_data["image_base64"] = None

        return JSONResponse(content=response_data)

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in get_user: {str(e)}")
        print(f"Error type: {type(e)}")
        print(f"Error traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get('/user/image/{user_id}')
def get_user_image(
    user_id: int, 
    is_quick_register: bool = Query(False),  # Add query parameter
    db: Session = Depends(get_db)
):
    try:
        if not is_quick_register:
            # Check regular users
            user = db.query(models.User).filter(models.User.user_id == user_id).first()
            if user:
                image_path = user.image_path
            else:
                raise HTTPException(status_code=404, detail="Regular user not found")
        else:
            # Check quick register users
            quick_user = db.query(models.QuickRegister).filter(models.QuickRegister.register_id == user_id).first()
            if quick_user:
                image_path = quick_user.image_path
            else:
                raise HTTPException(status_code=404, detail="Quick register user not found")
        
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image not found")
        
        return FileResponse(
            image_path,
            media_type="image/jpeg",
            filename=f"user_{user_id}_image.jpg"
        )
    
    except Exception as e:
        print(f"Error serving image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

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

# New route to create an institution
@app.post("/institutions/")
def create_institution(
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_institution = db.query(models.Institution).filter(models.Institution.name == name).first()
    if existing_institution:
        raise HTTPException(status_code=400, detail="Institution already exists")
    
    new_institution = models.Institution(name=name)
    db.add(new_institution)
    db.commit()
    db.refresh(new_institution)
    return new_institution

@app.post("/quick-register")
def quick_register(
    name: str = Form(...),
    email: str = Form(...),
    aadhar_number: str = Form(None),
    image: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Check if email exists in both tables
    existing_user = db.query(models.User).filter(models.User.email == email).first()
    existing_quick = db.query(models.QuickRegister).filter(models.QuickRegister.email == email).first()
    
    if existing_user or existing_quick:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check Aadhar if provided
    if aadhar_number:
        existing_aadhar_user = db.query(models.User).filter(models.User.aadhar_number == aadhar_number).first()
        existing_aadhar_quick = db.query(models.QuickRegister).filter(models.QuickRegister.aadhar_number == aadhar_number).first()
        if existing_aadhar_user or existing_aadhar_quick:
            raise HTTPException(status_code=400, detail="Aadhar number already registered")

    # Save image
    image_filename = f"quick_{uuid4().hex}_{image.filename}"
    image_path = os.path.join(UPLOAD_DIR, image_filename)
    
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    try:
        # Create quick register entry
        new_quick_register = models.QuickRegister(
            name=name,
            email=email,
            aadhar_number=aadhar_number,
            image_path=image_path
        )
        
        db.add(new_quick_register)
        db.commit()
        db.refresh(new_quick_register)

        return {
            "register_id": new_quick_register.register_id,
            "name": new_quick_register.name,
            "email": new_quick_register.email,
            "aadhar_number": new_quick_register.aadhar_number,
            "image_path": new_quick_register.image_path,
            "created_at": new_quick_register.created_at
        }

    except Exception as e:
        print(f"Error in quick registration: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error in quick registration: {str(e)}")

# @app.post("/institutions")


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
