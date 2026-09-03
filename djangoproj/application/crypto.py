import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _get_fernet() -> Fernet:
    """
    Derives a deterministic 256-bit (32-byte) key from Django's SECRET_KEY using SHA-256,
    then returns a Fernet cipher instance for authenticated symmetric encryption (AES-128-CBC + HMAC-SHA256).
    """
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_credential(raw_value: str) -> str:
    """
    Encrypts a plaintext credential string (e.g. IMAP password or Gemini API key).
    Returns a URL-safe base64-encoded ciphertext string prefixed with 'enc::'.
    """
    if not raw_value:
        return ""
    # Avoid double encryption
    if raw_value.startswith("enc::"):
        return raw_value
    
    cipher = _get_fernet()
    encrypted_bytes = cipher.encrypt(raw_value.encode("utf-8"))
    return f"enc::{encrypted_bytes.decode('utf-8')}"


def decrypt_credential(stored_value: str) -> str:
    """
    Decrypts an encrypted credential.
    If the value starts with 'enc::', strips prefix and decrypts via Fernet.
    If not prefixed (legacy plaintext during migration), returns as-is.
    """
    if not stored_value:
        return ""
    if not stored_value.startswith("enc::"):
        # Legacy unencrypted plaintext fallback
        return stored_value
    
    raw_ciphertext = stored_value[5:]
    try:
        cipher = _get_fernet()
        decrypted_bytes = cipher.decrypt(raw_ciphertext.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except (InvalidToken, Exception):
        # In case of corruption or altered SECRET_KEY, return empty or safe fallback
        return ""
