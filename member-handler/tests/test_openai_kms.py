"""Unit tests for OpenAI KMS encryption/decryption helpers."""
import pytest
import sys
import os
import base64
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from connectors.openai_kms import (
    encrypt_openai_key,
    decrypt_openai_key,
    EncryptionError,
    DecryptionError,
    _build_encryption_context,
)


class TestBuildEncryptionContext:
    """Tests for _build_encryption_context helper."""

    def test_valid_inputs(self):
        """Returns dict with memberEmail and accountId."""
        ctx = _build_encryption_context('user@example.com', 'openai-org-abc')
        assert ctx == {'memberEmail': 'user@example.com', 'accountId': 'openai-org-abc'}

    def test_empty_email_raises(self):
        """Raises ValueError when member_email is empty."""
        with pytest.raises(ValueError, match="member_email"):
            _build_encryption_context('', 'openai-org-abc')

    def test_empty_account_id_raises(self):
        """Raises ValueError when account_id is empty."""
        with pytest.raises(ValueError, match="account_id"):
            _build_encryption_context('user@example.com', '')

    def test_none_email_raises(self):
        """Raises ValueError when member_email is None."""
        with pytest.raises(ValueError, match="member_email"):
            _build_encryption_context(None, 'openai-org-abc')

    def test_none_account_id_raises(self):
        """Raises ValueError when account_id is None."""
        with pytest.raises(ValueError, match="account_id"):
            _build_encryption_context('user@example.com', None)


class TestEncryptOpenaiKeyDevMode:
    """Tests for encrypt_openai_key when KMS_KEY_ARN is not set (dev mode)."""

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_returns_base64(self):
        """In dev mode, returns base64-encoded plaintext."""
        key = 'sk-org-' + 'a' * 33  # 40 chars
        result = encrypt_openai_key(key, 'user@test.com', 'acct-123')
        decoded = base64.b64decode(result.encode('utf-8')).decode('utf-8')
        assert decoded == key

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_empty_key_raises(self):
        """Raises EncryptionError if plaintext_key is empty."""
        with pytest.raises(EncryptionError):
            encrypt_openai_key('', 'user@test.com', 'acct-123')

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_none_key_raises(self):
        """Raises EncryptionError if plaintext_key is None."""
        with pytest.raises(EncryptionError):
            encrypt_openai_key(None, 'user@test.com', 'acct-123')


class TestEncryptOpenaiKeyWithKMS:
    """Tests for encrypt_openai_key when KMS is configured."""

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_calls_kms_with_encryption_context(self, mock_boto3):
        """KMS encrypt is called with correct encryption context."""
        mock_kms = MagicMock()
        mock_kms.encrypt.return_value = {
            'CiphertextBlob': b'encrypted-data-blob'
        }
        mock_boto3.client.return_value = mock_kms

        key = 'sk-org-' + 'a' * 33
        result = encrypt_openai_key(key, 'user@test.com', 'openai-org-123')

        mock_kms.encrypt.assert_called_once_with(
            KeyId='arn:aws:kms:us-east-1:123456789:key/test-key',
            Plaintext=key.encode('utf-8'),
            EncryptionContext={'memberEmail': 'user@test.com', 'accountId': 'openai-org-123'}
        )
        # Result should be base64-encoded ciphertext
        assert result == base64.b64encode(b'encrypted-data-blob').decode('utf-8')

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_kms_failure_raises_encryption_error(self, mock_boto3):
        """Raises EncryptionError when KMS call fails."""
        mock_kms = MagicMock()
        mock_kms.encrypt.side_effect = Exception("KMS service error")
        mock_boto3.client.return_value = mock_kms

        key = 'sk-org-' + 'a' * 33
        with pytest.raises(EncryptionError, match="Unable to encrypt credentials"):
            encrypt_openai_key(key, 'user@test.com', 'openai-org-123')

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_plaintext_not_in_error_message(self, mock_boto3):
        """The plaintext key never appears in the error message."""
        mock_kms = MagicMock()
        mock_kms.encrypt.side_effect = Exception("KMS service error")
        mock_boto3.client.return_value = mock_kms

        key = 'sk-org-' + 'sensitivedata' * 5
        with pytest.raises(EncryptionError) as exc_info:
            encrypt_openai_key(key, 'user@test.com', 'openai-org-123')
        assert key not in str(exc_info.value)
        assert 'sensitivedata' not in str(exc_info.value)


class TestDecryptOpenaiKeyDevMode:
    """Tests for decrypt_openai_key when KMS_KEY_ARN is not set (dev mode)."""

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_decodes_base64(self):
        """In dev mode, decodes base64 to get plaintext."""
        key = 'sk-org-' + 'a' * 33
        encrypted = base64.b64encode(key.encode('utf-8')).decode('utf-8')
        result = decrypt_openai_key(encrypted, 'user@test.com', 'acct-123')
        assert result == key

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_empty_encrypted_key_raises(self):
        """Raises DecryptionError if encrypted_key is empty."""
        with pytest.raises(DecryptionError, match="inaccessible"):
            decrypt_openai_key('', 'user@test.com', 'acct-123')

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_dev_mode_invalid_base64_raises(self):
        """Raises DecryptionError if encrypted_key is not valid base64."""
        with pytest.raises(DecryptionError, match="inaccessible"):
            decrypt_openai_key('not-valid-base64!!!', 'user@test.com', 'acct-123')


class TestDecryptOpenaiKeyWithKMS:
    """Tests for decrypt_openai_key when KMS is configured."""

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_calls_kms_with_encryption_context(self, mock_boto3):
        """KMS decrypt is called with correct encryption context."""
        plaintext_key = 'sk-proj-' + 'b' * 32
        mock_kms = MagicMock()
        mock_kms.decrypt.return_value = {
            'Plaintext': plaintext_key.encode('utf-8')
        }
        mock_boto3.client.return_value = mock_kms

        ciphertext_blob = b'encrypted-data-blob'
        encrypted = base64.b64encode(ciphertext_blob).decode('utf-8')

        result = decrypt_openai_key(encrypted, 'user@test.com', 'openai-org-456')

        mock_kms.decrypt.assert_called_once_with(
            CiphertextBlob=ciphertext_blob,
            KeyId='arn:aws:kms:us-east-1:123456789:key/test-key',
            EncryptionContext={'memberEmail': 'user@test.com', 'accountId': 'openai-org-456'}
        )
        assert result == plaintext_key

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_kms_failure_raises_decryption_error(self, mock_boto3):
        """Raises DecryptionError when KMS call fails."""
        mock_kms = MagicMock()
        mock_kms.decrypt.side_effect = Exception("InvalidCiphertextException")
        mock_boto3.client.return_value = mock_kms

        encrypted = base64.b64encode(b'some-ciphertext').decode('utf-8')
        with pytest.raises(DecryptionError, match="inaccessible"):
            decrypt_openai_key(encrypted, 'user@test.com', 'openai-org-456')

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_ciphertext_not_in_error_message(self, mock_boto3):
        """The ciphertext never appears in the error message."""
        mock_kms = MagicMock()
        mock_kms.decrypt.side_effect = Exception("KMS access denied")
        mock_boto3.client.return_value = mock_kms

        ciphertext = base64.b64encode(b'sensitive-cipher-blob').decode('utf-8')
        with pytest.raises(DecryptionError) as exc_info:
            decrypt_openai_key(ciphertext, 'user@test.com', 'openai-org-456')
        assert ciphertext not in str(exc_info.value)
        assert 'sensitive-cipher-blob' not in str(exc_info.value)
        assert 'KMS access denied' not in str(exc_info.value)

    @patch('connectors.openai_kms.KMS_KEY_ARN', 'arn:aws:kms:us-east-1:123456789:key/test-key')
    @patch('connectors.openai_kms.boto3')
    def test_none_encrypted_key_raises(self, mock_boto3):
        """Raises DecryptionError if encrypted_key is None."""
        with pytest.raises(DecryptionError, match="inaccessible"):
            decrypt_openai_key(None, 'user@test.com', 'openai-org-456')


class TestEncryptDecryptRoundTrip:
    """Integration tests verifying encrypt → decrypt round-trip in dev mode."""

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_roundtrip_preserves_key(self):
        """Encrypting then decrypting returns the original key."""
        key = 'sk-org-' + 'roundtrip123' * 4
        email = 'roundtrip@test.com'
        acct = 'openai-roundtrip-acct'

        encrypted = encrypt_openai_key(key, email, acct)
        decrypted = decrypt_openai_key(encrypted, email, acct)
        assert decrypted == key

    @patch('connectors.openai_kms.KMS_KEY_ARN', '')
    def test_encrypted_value_differs_from_plaintext(self):
        """The encrypted value should not be the same as plaintext."""
        key = 'sk-proj-' + 'a' * 32
        encrypted = encrypt_openai_key(key, 'user@test.com', 'acct-1')
        assert encrypted != key
