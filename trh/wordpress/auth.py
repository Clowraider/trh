"""WordPress REST API authentication helpers."""

import base64


def build_wp_auth_headers(wp_username: str, wp_app_password: str) -> dict[str, str]:
    """Build Basic Auth headers for the WordPress REST API.

    WordPress Application Passwords use Basic Auth:
      - Combine username:app_password
      - Base64-encode the credentials
      - Send as Authorization: Basic <base64>
    """
    if not wp_username or not wp_app_password:
        raise RuntimeError("Faltan credenciales de WordPress (usuario o application password).")

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
    }
