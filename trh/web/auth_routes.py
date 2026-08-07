"""Authentication routes (login/logout) for the TRH web panel."""

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session as flask_session,
    url_for,
)

from trh.auth.csrf import generate_csrf_token
from trh.auth.decorators import require_auth
from trh.auth.passwords import verify_password
from trh.auth.rate_limiter import RateLimiter
from trh.auth.repository import get_user_by_username, update_last_login
from trh.auth.sessions import (
    create_session_for_user,
    delete_session,
    set_session_cookie,
)

bp = Blueprint("auth", __name__, url_prefix="/auth")

_username_limiter = RateLimiter(max_attempts=5, window_minutes=5)
_ip_limiter = RateLimiter(max_attempts=20, window_minutes=5)


def _login_error(message: str, status: int, next_url: str):
    flash(message, "danger")
    return (
        render_template(
            "auth/login.html",
            csrf_token=flask_session.get("csrf_token"),
            next=next_url,
        ),
        status,
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next") or url_for("index")

    if request.method == "GET":
        csrf_token = generate_csrf_token()
        flask_session["csrf_token"] = csrf_token
        return render_template("auth/login.html", csrf_token=csrf_token, next=next_url)

    usuario = (request.form.get("usuario") or "").strip()
    password = request.form.get("password") or ""

    client_ip = request.remote_addr or "unknown"
    if not _username_limiter.is_allowed(f"username:{usuario}"):
        return _login_error(
            "Demasiados intentos fallidos para este usuario. Intente más tarde.",
            429,
            next_url,
        )
    if not _ip_limiter.is_allowed(f"ip:{client_ip}"):
        return _login_error(
            "Demasiados intentos fallidos desde esta red. Intente más tarde.",
            429,
            next_url,
        )

    user = get_user_by_username(usuario)
    if user is None or not verify_password(password, user["password_hash"]):
        return _login_error("Usuario o contraseña incorrectos.", 401, next_url)

    update_last_login(user["id"])
    session_token, _csrf_token, expires_at = create_session_for_user(
        user_id=user["id"],
        lifetime_hours=current_app.config.get("SESSION_LIFETIME_HOURS", 24),
        request_obj=request,
    )

    response = redirect(next_url)
    set_session_cookie(
        response,
        session_token,
        expires_at=expires_at,
        secure=current_app.config.get(
            "SESSION_COOKIE_SECURE", not current_app.debug
        ),
    )
    return response


@bp.route("/logout", methods=["POST"])
@require_auth
def logout():
    session_token = request.cookies.get("session_token")
    delete_session(session_token)
    response = redirect(url_for("auth.login"))
    response.delete_cookie("session_token", path="/")
    return response
