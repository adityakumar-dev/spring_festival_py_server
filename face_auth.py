import face_recognition

def is_face_match(stored_image_path, test_image_path):
    """Compare a stored face with a test image and return True/False."""
    # Load and encode stored image
    stored_image = face_recognition.load_image_file(stored_image_path)
    stored_encodings = face_recognition.face_encodings(stored_image)
    
    if not stored_encodings:
        return False  # No face detected in stored image

    # Load and encode test image
    test_image = face_recognition.load_image_file(test_image_path)
    test_encodings = face_recognition.face_encodings(test_image)
    
    if not test_encodings:
        return False  # No face detected in test image

    # Compare faces
    return face_recognition.compare_faces([stored_encodings[0]], test_encodings[0])[0]

# Example Usage:
# print(is_face_match("user_face.jpg", "test_face.jpg"))
