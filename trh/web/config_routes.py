"""Per-user configuration routes for the TRH web panel."""

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from trh.auth.decorators import require_auth
from trh.sources.repository import (
    get_subscribed_source_ids,
    list_active_sources,
    subscribe_user_to_sources,
)
from trh.wordpress.repository import (
    get_wordpress_config_by_user,
    upsert_wordpress_config,
)
from trh.wordpress.validator import validate_wordpress_credentials

bp = Blueprint("config", __name__, url_prefix="/config")


def _validate_wordpress_form(form):
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


def _selected_source_ids_from_form(form):
    ids = set()
    for raw in form.getlist("source_ids"):
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    return ids


def _render_config_page(config=None, subscribed_source_ids=None, status_code=200):
    user_id = g.current_user.get("user_id")
    return render_template(
        "config/index.html",
        config=config if config is not None else get_wordpress_config_by_user(user_id),
        sources=list_active_sources(),
        subscribed_source_ids=(
            subscribed_source_ids
            if subscribed_source_ids is not None
            else get_subscribed_source_ids(user_id)
        ),
    ), status_code


@bp.route("", methods=["GET"])
@require_auth
def index():
    return _render_config_page()


@bp.route("/fuentes", methods=["POST"])
@require_auth
def save_sources():
    """Save news source subscriptions independently of WordPress config."""
    user_id = g.current_user.get("user_id")
    selected_source_ids = _selected_source_ids_from_form(request.form)

    try:
        subscribe_user_to_sources(user_id, list(selected_source_ids))
    except ValueError as exc:
        flash(str(exc), "danger")
        return _render_config_page(subscribed_source_ids=selected_source_ids, status_code=400)

    flash("Fuentes de noticias guardadas correctamente.", "success")
    return redirect(url_for("config.index"))


@bp.route("/wordpress", methods=["POST"])
@require_auth
def save_wordpress():
    """Save WordPress configuration independently of source subscriptions."""
    user_id = g.current_user.get("user_id")
    config = get_wordpress_config_by_user(user_id)

    errors, wp_url, wp_username, wp_app_password = _validate_wordpress_form(request.form)
    if errors:
        for error in errors:
            flash(error, "danger")
        return _render_config_page(
            config={
                "wp_url": wp_url,
                "wp_username": wp_username,
                "wp_app_password": "",
            },
            status_code=400,
        )

    ok, message = validate_wordpress_credentials(
        wp_url,
        wp_username,
        wp_app_password,
    )
    if not ok:
        flash(message, "danger")
        return _render_config_page(
            config={
                "wp_url": wp_url,
                "wp_username": wp_username,
                "wp_app_password": "",
            },
            status_code=400,
        )

    upsert_wordpress_config(
        user_id=user_id,
        wp_url=wp_url,
        wp_username=wp_username,
        wp_app_password=wp_app_password,
    )
    flash("Configuración de WordPress guardada correctamente.", "success")
    return redirect(url_for("config.index"))
