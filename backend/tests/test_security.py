import io
import os
import sys
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-must-be-at-least-32-bytes-long")
os.environ.setdefault("LOGIN_PASSWORD", "test-login-password")

import auth_service
import main
import ocr_service
from routers import auth as auth_router
from routers import ocr as ocr_router


def _auth_headers():
    token = auth_service.create_jwt("security-test", "安全测试")
    return {"Authorization": f"Bearer {token}"}


def _png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "#ffffff").save(output, format="PNG")
    return output.getvalue()


class TestAuthenticationSecurity(unittest.TestCase):
    def test_short_jwt_secret_is_rejected(self):
        with patch.object(auth_service, "JWT_SECRET", "short"):
            with self.assertRaises(RuntimeError):
                auth_service.validate_auth_configuration()

    def test_safe_next_path_rejects_external_redirects(self):
        self.assertEqual(auth_router._safe_next_path("https://evil.example/x"), "/")
        self.assertEqual(auth_router._safe_next_path("//evil.example/x"), "/")
        self.assertEqual(auth_router._safe_next_path("/inventory?alert=1"), "/inventory?alert=1")

    def test_password_login_is_rate_limited(self):
        auth_router._login_failures.clear()
        try:
            with TestClient(main.app) as client:
                for _ in range(auth_router.LOGIN_MAX_FAILURES):
                    response = client.post(
                        "/api/auth/login",
                        json={"password": "wrong-password"},
                    )
                    self.assertEqual(response.status_code, 401)
                blocked = client.post(
                    "/api/auth/login",
                    json={"password": "wrong-password"},
                )
                self.assertEqual(blocked.status_code, 429)
        finally:
            auth_router._login_failures.clear()

    def test_oauth_callback_redirect_contains_code_not_jwt(self):
        previous_base = os.environ.get("APP_BASE_URL")
        os.environ["APP_BASE_URL"] = "http://testserver"
        try:
            with patch.object(auth_router, "is_wecom_configured", return_value=True):
                with TestClient(main.app) as client:
                    start = client.get("/api/auth/wecom/url", params={"redirect": "/camera"})
                    self.assertEqual(start.status_code, 200)
                    state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
                    state_as_access = client.get(
                        "/api/inventory",
                        headers={"Authorization": f"Bearer {state}"},
                    )
                    self.assertEqual(state_as_access.status_code, 401)
                    callback = client.get(
                        "/api/auth/wecom/callback",
                        params={"code": "temporary-code", "state": state},
                        follow_redirects=False,
                    )
                    self.assertEqual(callback.status_code, 307)
                    location = callback.headers["location"]
                    self.assertIn("code=temporary-code", location)
                    self.assertIn("state=", location)
                    self.assertNotIn("token=", location)
        finally:
            if previous_base is None:
                os.environ.pop("APP_BASE_URL", None)
            else:
                os.environ["APP_BASE_URL"] = previous_base


class TestUploadSecurity(unittest.TestCase):
    def test_html_disguised_as_image_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            ocr_router._normalize_image(b"<script>alert(1)</script>")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_valid_image_is_reencoded_as_jpeg(self):
        normalized = ocr_router._normalize_image(_png_bytes())
        self.assertTrue(normalized.startswith(b"\xff\xd8\xff"))
        with Image.open(io.BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")

    def test_ocr_upload_and_image_access_require_auth(self):
        async def fake_recognize(_content):
            return {"raw_text": "", "parsed": {}, "confidence": True}

        created_path = None
        try:
            with patch.object(ocr_service, "recognize_image", fake_recognize):
                with TestClient(main.app) as client:
                    unauth = client.post(
                        "/api/ocr",
                        files={"file": ("label.png", _png_bytes(), "image/png")},
                    )
                    self.assertEqual(unauth.status_code, 401)

                    upload = client.post(
                        "/api/ocr",
                        headers=_auth_headers(),
                        files={"file": ("label.png", _png_bytes(), "image/png")},
                    )
                    self.assertEqual(upload.status_code, 200, upload.text)
                    filename = upload.json()["image_path"]
                    self.assertTrue(filename.endswith(".jpg"))
                    created_path = os.path.join(ocr_router.UPLOAD_DIR, filename)
                    for _ in range(20):
                        if os.path.exists(created_path):
                            break
                        time.sleep(0.05)

                    self.assertEqual(client.get(f"/api/uploads/{filename}").status_code, 401)
                    served = client.get(f"/api/uploads/{filename}", headers=_auth_headers())
                    self.assertEqual(served.status_code, 200)
                    self.assertEqual(served.headers["content-type"], "image/jpeg")
                    self.assertTrue(served.content.startswith(b"\xff\xd8\xff"))
        finally:
            if created_path and os.path.exists(created_path):
                os.unlink(created_path)


if __name__ == "__main__":
    unittest.main()
