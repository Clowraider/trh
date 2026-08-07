"""Per-user configuration routes for the TRH web panel."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from trh.auth.decorators import require_auth
from trh.wordpress.repository import (
    get_wordpress_config_by_user,
    upsert_wordpress_config,
)
from trh.wordpress.validator import validate_wordpress_credentials

bp = Blueprint("config", __name__, url_prefix="/config")

_FAKE_NEWS_SOURCES = [
    ("el_liberal", "El Liberal"),
    ("nuevo_diario", "Nuevo Diario"),
    ("la_voz", "La Voz del Interior"),
    ("clarin", "Clarín"),
    ("lanacion", "La Nación"),
    ("infobae", "Infobae"),
]


def _validate_config_form(form):
    errors = []

    wp_url = (form.get("wp_url") or "").strip()
    wp_username = (form.get("wp_username") or "").strip()
    wp_app_password = form.get("wp_app_password") or ""
    wp_app_password_confirm = form.get("wp_app_password_confirm") or ""

    if not wp_url:
        errors.append("La URL de WordPress es obligatoria.")
    if not wp_username:
        errors.append("El usuario de WordPress es obligatorio.")
    if not wp_app_password:
        errors.append("La contraseña de aplicación es obligatoria.")
    if wp_app_password != wp_app_password_confirm:
        errors.append("Las contraseñas de aplicación no coinciden.")

    return errors, wp_url, wp_username, wp_app_password


@bp.route("", methods=["GET", "POST"])
@require_auth
def index():
    user_id = g.current_user.get("user_id")
    config = get_wordpress_config_by_user(user_id)

    if request.method == "GET":
        return render_template(
            "config/index.html",
            config=config,
            news_sources=_FAKE_NEWS_SOURCES,
        )

    errors, wp_url, wp_username, wp_app_password = _validate_config_form(request.form)
    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "config/index.html",
            config={
                "wp_url": wp_url,
                "wp_username": wp_username,
                "wp_app_password": "",
            },
            news_sources=_FAKE_NEWS_SOURCES,
        ), 400

    ok, message = validate_wordpress_credentials(
        wp_url,
        wp_username,
        wp_app_password,
    )
    if not ok:
        flash(message, "danger")
        return render_template(
            "config/index.html",
            config={
                "wp_url": wp_url,
                "wp_username": wp_username,
                "wp_app_password": "",
            },
            news_sources=_FAKE_NEWS_SOURCES,
        ), 400

    upsert_wordpress_config(
        user_id=user_id,
        wp_url=wp_url,
        wp_username=wp_username,
        wp_app_password=wp_app_password,
    )
    flash("Configuración de WordPress guardada correctamente.", "success")
    return redirect(url_for("config.index"))
