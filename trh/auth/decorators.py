"""Flask decorators for authentication and authorization."""

from functools import wraps

from flask import current_app, g, jsonify, redirect, request, url_for
from werkzeug.routing.exceptions import BuildError

from trh.auth.sessions import validate_session_token


def require_auth(view):
    """Require a valid session to access the view.

    When AUTH_REQUIRED is False the check is skipped to preserve existing
    behavior in test/legacy environments, but the decorator still wraps the
    view so it can be enabled by flipping the config.
    """

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_app.config.get("AUTH_REQUIRED", True):
            return view(*args, **kwargs)

        session_token = request.cookies.get("session_token")
        session = validate_session_token(session_token)
        if session is None:
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": "Unauthorized"}), 401
            try:
                login_url = url_for("auth.login", next=request.full_path)
            except BuildError:
                login_url = "/auth/login"
            return redirect(login_url)

        g.current_user = session
        return view(*args, **kwargs)

    return wrapped


def require_admin(view):
    """Require an authenticated admin user to access the view."""

    @wraps(view)
    def admin_check(*args, **kwargs):
        if not current_app.config.get("AUTH_REQUIRED", True):
            return view(*args, **kwargs)

        user = g.get("current_user")
        if user is None or not user.get("is_admin"):
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"error": "Forbidden"}), 403
            return "Forbidden", 403

        return view(*args, **kwargs)

    return require_auth(admin_check)
