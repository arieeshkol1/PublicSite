"""KMS credential encryption/decryption helpers."""
import os
import base64
import logging
import boto3

logger = logging.getLogger(__name__)

# KMS key ARN from environment (set by CloudFormation)
KMS_KEY_ARN = os.environ.get('CREDENTIAL_KMS_KEY_ARN', '')


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string with KMS. Returns base64-encoded ciphertext."""
    if not KMS_KEY_ARN:
        logger.warning("CREDENTIAL_KMS_KEY_ARN not set, storing credential unencrypted (dev mode)")
        return base64.b64encode(plaintext.encode('utf-8')).decode('utf-8')
    
    try:
        kms = boto3.client('kms')
        response = kms.encrypt(
            KeyId=KMS_KEY_ARN,
            Plaintext=plaintext.encode('utf-8')
        )
        return base64.b64encode(response['CiphertextBlob']).decode('utf-8')
    except Exception as e:
        logger.error(f"KMS encryption failed: {e}")
        raise RuntimeError("Unable to encrypt credentials. Please contact support.")


def decrypt_credential(ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded KMS ciphertext. Returns plaintext string."""
    if not KMS_KEY_ARN:
        # Dev mode fallback — treat as plain base64
        return base64.b64decode(ciphertext_b64.encode('utf-8')).decode('utf-8')
    
    try:
        kms = boto3.client('kms')
        ciphertext_blob = base64.b64decode(ciphertext_b64.encode('utf-8'))
        response = kms.decrypt(
            CiphertextBlob=ciphertext_blob,
            KeyId=KMS_KEY_ARN
        )
        plaintext = response['Plaintext'].decode('utf-8')
        return plaintext
    except Exception as e:
        logger.error(f"KMS decryption failed: {e}")
        raise RuntimeError("Unable to access stored credentials. Please contact support.")
