import unittest

from zara.login.jwt import create_jwt, verify_jwt


class TestJWT(unittest.TestCase):
    def test_create_and_verify_jwt(self):
        payload = {"user_id": "test_user"}
        roles = ["admin"]
        permissions = ["read", "write"]

        token = create_jwt(payload, roles=roles, permissions=permissions)
        verified_payload = verify_jwt(token)

        self.assertEqual(payload["user_id"], verified_payload["user_id"])
        self.assertEqual(roles, verified_payload["roles"])
        self.assertEqual(permissions, verified_payload["permissions"])

    def test_invalid_jwt(self):
        payload = {"user_id": "test_user"}
        token = create_jwt(payload)
        token += "invalid"
        verified_payload = verify_jwt(token)
        self.assertIsNone(verified_payload)
