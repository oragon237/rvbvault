import tempfile
import unittest
from pathlib import Path

from rvb_vault.security import LocalCipher, create_password_verifier, verify_password


class SecurityTests(unittest.TestCase):
    def test_encryption_round_trip_and_random_nonce(self):
        with tempfile.TemporaryDirectory() as tmp:
            cipher = LocalCipher(Path(tmp) / "key")
            first = cipher.encrypt("highly-secret")
            second = cipher.encrypt("highly-secret")
            self.assertNotEqual(first, second)
            self.assertNotIn(b"highly-secret", first)
            self.assertEqual(cipher.decrypt(first), b"highly-secret")

    def test_password_verifier(self):
        verifier = create_password_verifier("correct horse")
        self.assertTrue(verify_password("correct horse", verifier))
        self.assertFalse(verify_password("wrong", verifier))


if __name__ == "__main__":
    unittest.main()

