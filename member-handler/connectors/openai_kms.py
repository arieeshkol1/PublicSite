"""OpenAI-specific KMS encryption/decryption helpers.

Wraps the base KMS helpers with encryption context containing member email
and account ID, ensuring that encrypted keys can only be decrypted with
the same context they were encrypted with.

Security guarantees:
- Plaintext API key is never stored in any field or log output
- Decrypted values are not cached beyond the request scope
- On encryption failure: caller must NOT persist the record
- On decryption failure: ciphertext is never exposed in errors
"""
import os
import base64
import logging
import boto3

logger = logging.getLogger(__name__)

# KMS key ARN from environment (set by CloudFormation)
KMS_KEY_ARN = os.environ.get('CREDENTIAL_KMS_KEY_ARN', '')


class EncryptionError(Exception):
    """Raised when KMS encryption fails. Caller must NOT persist the record."""
    pass


class DecryptionError(Exception):
    """Raised when KMS decryption fails. Ciphertext must not be exposed."""
    pass


def _build_encryption_context(member_email: str, account_id: str) -> dict:
    """Build the encryption context dict for OpenAI key operations.

    Args:
        member_email: The member's email address.
        account_id: The OpenAI account/org identifier.

    Returns:
        Encryption context dict with memberEmail and accountId.

    Raises:
        ValueError: If either parameter is empty or not a string.
    """
    if not member_email or not isinstance(member_email, str):
        raise ValueError("member_email must be a non-empty string")
    if not account_id or not isinstance(account_id, str):
        raise ValueError("account_id must be a non-empty string")

    return {
        'memberEmail': member_email,
        'accountId': account_id,
    }


def encrypt_openai_key(plaintext_key: str, member_email: str, account_id: str) -> str:
    """Encrypt an OpenAI API key with KMS using member-specific encryption context.

    The encryption context ties the ciphertext to a specific member and account,
    preventing decryption with a different context.

    Args:
        plaintext_key: The raw OpenAI API key (e.g., sk-org-... or sk-proj-...).
        member_email: The member's email address (used in encryption context).
        account_id: The OpenAI account identifier (used in encryption context).

    Returns:
        Base64-encoded ciphertext string suitable for storage in DynamoDB.

    Raises:
        EncryptionError: If KMS encryption fails. The caller must NOT persist
            any record containing the plaintext key.
    """
    if not plaintext_key or not isinstance(plaintext_key, str):
        raise EncryptionError("Unable to encrypt credentials: invalid key provided.")

    encryption_context = _build_encryption_context(member_email, account_id)

    if not KMS_KEY_ARN:
        # Dev mode fallback — encode with base64 (no real encryption)
        logger.warning(
            "CREDENTIAL_KMS_KEY_ARN not set, using base64 encoding (dev mode only)"
        )
        return base64.b64encode(plaintext_key.encode('utf-8')).decode('utf-8')

    try:
        kms = boto3.client('kms')
        response = kms.encrypt(
            KeyId=KMS_KEY_ARN,
            Plaintext=plaintext_key.encode('utf-8'),
            EncryptionContext=encryption_context
        )
        ciphertext = base64.b64encode(response['CiphertextBlob']).decode('utf-8')
        # Never log the plaintext key or full ciphertext
        logger.info(
            "Successfully encrypted OpenAI API key for account %s",
            account_id
        )
        return ciphertext
    except Exception as e:
        # Log error without exposing the plaintext key
        logger.error(
            "KMS encryption failed for account %s: %s",
            account_id, type(e).__name__
        )
        raise EncryptionError(
            "Unable to encrypt credentials. Please contact support."
        )


def decrypt_openai_key(encrypted_key: str, member_email: str, account_id: str) -> str:
    """Decrypt a stored OpenAI API key using KMS with member-specific encryption context.

    The decrypted value must NOT be cached beyond the current request scope.

    Args:
        encrypted_key: Base64-encoded KMS ciphertext from DynamoDB.
        member_email: The member's email address (must match encryption context).
        account_id: The OpenAI account identifier (must match encryption context).

    Returns:
        The plaintext OpenAI API key string.

    Raises:
        DecryptionError: If KMS decryption fails. The error message never
            exposes the ciphertext or internal error details.
    """
    if not encrypted_key or not isinstance(encrypted_key, str):
        raise DecryptionError(
            "Credentials inaccessible. Please re-add your OpenAI connection."
        )

    encryption_context = _build_encryption_context(member_email, account_id)

    if not KMS_KEY_ARN:
        # Dev mode fallback — decode base64
        try:
            return base64.b64decode(encrypted_key.encode('utf-8')).decode('utf-8')
        except Exception:
            raise DecryptionError(
                "Credentials inaccessible. Please re-add your OpenAI connection."
            )

    try:
        kms = boto3.client('kms')
        ciphertext_blob = base64.b64decode(encrypted_key.encode('utf-8'))
        response = kms.decrypt(
            CiphertextBlob=ciphertext_blob,
            KeyId=KMS_KEY_ARN,
            EncryptionContext=encryption_context
        )
        plaintext = response['Plaintext'].decode('utf-8')
        logger.info(
            "Successfully decrypted OpenAI API key for account %s",
            account_id
        )
        return plaintext
    except Exception as e:
        # Never expose ciphertext or internal error details
        logger.error(
            "KMS decryption failed for account %s: %s",
            account_id, type(e).__name__
        )
        raise DecryptionError(
            "Credentials inaccessible. Please re-add your OpenAI connection."
        )
