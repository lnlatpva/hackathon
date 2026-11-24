"""Минимальная реализация"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
import jwt


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 390_000)
    return 'pbkdf2_sha256$390000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt, digest = encoded.split('$')
        return algo == 'pbkdf2_sha256' and hmac.compare_digest(
            hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(iters)),
            base64.b64decode(digest),
        )
    except (ValueError, TypeError):
        return False


def token(user_id: str, secret: str) -> str:
    return jwt.encode({'sub': user_id, 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, secret, algorithm='HS256')


def user_id_from_token(value: str, secret: str) -> str:
    return str(jwt.decode(value, secret, algorithms=['HS256'], options={'require': ['sub','exp']})['sub'])