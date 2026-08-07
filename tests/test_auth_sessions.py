from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from trh.auth import sessions


@pytest.fixture(autouse=True)
def patch_repository():
    with (
        patch("trh.auth.sessions.repo_create_session") as mock_create,
        patch("trh.auth.sessions.repo_get_session_by_token") as mock_get,
        patch("trh.auth.sessions.repo_delete_session") as mock_delete,
    ):
        yield {
            "create": mock_create,
            "get": mock_get,
            "delete": mock_delete,
        }


def test_create_session_for_user_returns_tokens_and_calls_repository(patch_repository):
    request = MagicMock()
    request.remote_addr = "192.168.1.1"
    request.user_agent.string = "TestAgent/1.0"

    session_token, csrf_token, expires_at = sessions.create_session_for_user(
        user_id=1, lifetime_hours=24, request_obj=request
    )

    assert session_token
    assert csrf_token
    assert expires_at is not None
    assert session_token != csrf_token
    patch_repository["create"].assert_called_once()
    args = patch_repository["create"].call_args.kwargs
    assert args["user_id"] == 1
    assert args["ip_address"] == "192.168.1.1"
    assert args["user_agent"] == "TestAgent/1.0"
    assert args["csrf_token"] == csrf_token


def test_validate_session_token_returns_data_for_valid_token(patch_repository):
    future = datetime.utcnow() + timedelta(hours=1)
    patch_repository["get"].return_value = {
        "session_token": "token",
        "expires_at": future,
        "usuario": "admin",
        "is_admin": True,
    }

    result = sessions.validate_session_token("token")

    assert result["usuario"] == "admin"
    assert result["is_admin"] is True
    patch_repository["delete"].assert_not_called()


def test_validate_session_token_returns_none_for_missing_token(patch_repository):
    patch_repository["get"].return_value = None

    assert sessions.validate_session_token("token") is None


def test_validate_session_token_deletes_expired_token(patch_repository):
    past = datetime.utcnow() - timedelta(hours=1)
    patch_repository["get"].return_value = {
        "session_token": "token",
        "expires_at": past,
    }

    assert sessions.validate_session_token("token") is None
    patch_repository["delete"].assert_called_once_with("token")


def test_delete_session_calls_repository(patch_repository):
    sessions.delete_session("token")

    patch_repository["delete"].assert_called_once_with("token")


def test_delete_session_is_noop_for_none(patch_repository):
    sessions.delete_session(None)

    patch_repository["delete"].assert_not_called()
