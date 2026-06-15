from functools import wraps
from flask import g, request, jsonify
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
            parts = auth_header.split(' ', 1)
            if len(parts) != 2 or parts[0] != 'Bearer':
                return jsonify({'error': 'Malformed Authorization header'}), 401
            token = parts[1]

            # Verify the token
            decoded_token = auth.verify_id_token(token)
            user_id = decoded_token['uid']

            # Store on flask.g so JunoLogger / SessionIdFilter pick it up
            # automatically on every structured log call in this request.
            g.user_id = user_id

            # Also pass as a kwarg for route handlers that need it explicitly
            kwargs['user_id'] = user_id

            return f(*args, **kwargs)

        except Exception as e:
            return jsonify({'error': 'Invalid or expired token', 'details': str(e)}), 401

    return decorated_function
