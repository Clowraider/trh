from unittest.mock import MagicMock, patch

import pytest
import requests

from trh.wordpress.validator import validate_wordpress_credentials


@pytest.fixture
def mock_requests_request():
    with patch("trh.wordpress.validator.requests.request") as mock:
        yield mock


def test_validate_wordpress_credentials_rejects_empty_url(mock_requests_request):
    ok, message = validate_wordpress_credentials("", "user", "pass")

    assert ok is False
    assert "URL" in message
    mock_requests_request.assert_not_called()


def test_validate_wordpress_credentials_rejects_empty_credentials(mock_requests_request):
    ok, message = validate_wordpress_credentials("https://wp.test", "", "")

    assert ok is False
    assert "usuario" in message.lower()
    mock_requests_request.assert_not_called()


def test_validate_wordpress_credentials_success(mock_requests_request):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_requests_request.return_value = mock_response

    ok, message = validate_wordpress_credentials(
        "https://wp.test/", "admin", "app-password"
    )

    assert ok is True
    mock_requests_request.assert_called_once()
    call_args = mock_requests_request.call_args
    assert call_args.kwargs["headers"]["Authorization"].startswith("Basic ")
    assert call_args.args[1] == "https://wp.test/wp-json/wp/v2/users/me"


def test_validate_wordpress_credentials_401_shows_app_password_hint(mock_requests_request):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_requests_request.return_value = mock_response

    ok, message = validate_wordpress_credentials(
        "https://wp.test/", "admin", "wrong-password"
    )

    assert ok is False
    assert "Clave de Aplicación" in message
    assert "Application Password" in message


def test_validate_wordpress_credentials_connection_error(mock_requests_request):
    mock_requests_request.side_effect = requests.ConnectionError("No route to host")

    ok, message = validate_wordpress_credentials(
        "https://wp.test/", "admin", "app-password"
    )

    assert ok is False
    assert "No se pudo conectar con WordPress" in message


def test_validate_wordpress_credentials_timeout(mock_requests_request):
    mock_requests_request.side_effect = requests.Timeout("Timeout")

    ok, message = validate_wordpress_credentials(
        "https://wp.test/", "admin", "app-password"
    )

    assert ok is False
    assert "tiempo de espera" in message.lower()
