from functools import wraps
from flask import request, jsonify
from firebase_admin import auth

def verify_firebase_token(f):
    """Decorator to verify Firebase ID token from Authorization header"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401
        
        try:
            # Extract token from "Bearer <token>"
            token = auth_header.split('Bearer ')[-1]
            
            # Verify the token
            decoded_token = auth.verify_id_token(token)
            
            # Add user_id to kwargs for route handlers to use
            kwargs['user_id'] = decoded_token['uid']
            
            return f(*args, **kwargs)
        
        except Exception as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401
    
    return decorated_function
