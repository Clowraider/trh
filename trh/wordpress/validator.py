"""WordPress credential validation helper."""

import requests

from trh.wordpress.auth import build_wp_auth_headers


def validate_wordpress_credentials(
    wp_url: str,
    wp_username: str,
    wp_app_password: str,
) -> tuple[bool, str]:
    """Test WordPress credentials. Return (ok, message)."""
    base_url = (wp_url or "").rstrip("/")
    if not base_url:
        return False, "La URL de WordPress es obligatoria."
    if not wp_username or not wp_app_password:
        return False, "El usuario y la contraseña de aplicación son obligatorios."

    try:
        headers = build_wp_auth_headers(wp_username, wp_app_password)
    except RuntimeError as exc:
        return False, str(exc)

    url = f"{base_url}/wp-json/wp/v2/users/me"

    try:
        response = requests.request("GET", url, headers=headers, timeout=20)
    except requests.Timeout:
        return False, (
            "No se pudo conectar con WordPress: tiempo de espera agotado. "
            "Verificá la URL."
        )
    except requests.ConnectionError:
        return False, (
            "No se pudo conectar con WordPress. Verificá la URL y asegurate "
            "de usar una Clave de Aplicación (Application Password), no la "
            "contraseña de inicio de sesión de WordPress."
        )
    except requests.RequestException as exc:
        return False, f"No se pudo conectar con WordPress: {exc}"

    if response.status_code == 200:
        return True, "Conexión exitosa con WordPress."

    if response.status_code == 401:
        return False, (
            "No se pudo conectar con WordPress. Verificá la URL y asegurate "
            "de usar una Clave de Aplicación (Application Password), no la "
            "contraseña de inicio de sesión de WordPress."
        )

    return False, (
        f"No se pudo conectar con WordPress (HTTP {response.status_code}). "
        "Verificá la URL y las credenciales."
    )
