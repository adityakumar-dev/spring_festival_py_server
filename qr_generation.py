import qrcode
import os
import json
QR_DIR = "qrs"
os.makedirs(QR_DIR,exist_ok=True)

def generate_qr_code(user_id : int, name : str, email : str):
    # Create a dictionary with user data
    user_data = {
        "user_id": user_id,
        "name": name,
        "email": email
    }
    # Convert to JSON string
    qr_data = json.dumps(user_data)
    qr = qrcode.make(qr_data)
    qr_path = os.path.join(QR_DIR,f"qr_code_{user_id}.png")
    qr.save(qr_path)
    return qr_path

def generate_qr_codes(users : list[dict]):
    for user in users:
        user_data = {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"]
        }
        qr_data = json.dumps(user_data)
        qr_path = generate_qr_code(qr_data)
        print(f"QR code generated for {user['name']} at {qr_path}")
