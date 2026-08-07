"""Admin user management routes for the TRH web panel."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from trh.auth.decorators import require_admin
from trh.auth.passwords import hash_password
from trh.auth.repository import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    list_users,
    update_user_password,
)
from trh.auth.validation import (
    validate_email,
    validate_nombre,
    validate_notas,
    validate_password,
    validate_usuario,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _collect_user_form_errors(form):
    errors = []
    for field, validator in (
        ("usuario", validate_usuario),
        ("email", validate_email),
        ("nombre", validate_nombre),
        ("notas", validate_notas),
    ):
        error = validator(form.get(field))
        if error:
            errors.append(error)
    return errors


@bp.route("/usuarios")
@require_admin
def list_users_view():
    users = list_users()
    return render_template("admin/usuarios.html", users=users)


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@require_admin
def new_user():
    if request.method == "GET":
        return render_template("admin/usuario_nuevo.html")

    usuario = (request.form.get("usuario") or "").strip()
    email = (request.form.get("email") or "").strip()
    nombre = (request.form.get("nombre") or "").strip()
    password = request.form.get("password") or ""
    ciudad = (request.form.get("ciudad") or "").strip() or None
    provincia = (request.form.get("provincia") or "").strip() or None
    pais = (request.form.get("pais") or "").strip() or None
    notas = (request.form.get("notas") or "").strip() or None
    is_admin = request.form.get("is_admin") == "1"

    errors = _collect_user_form_errors({
        "usuario": usuario,
        "email": email,
        "nombre": nombre,
        "notas": notas,
    })
    password_error = validate_password(password)
    if password_error:
        errors.append(password_error)

    if get_user_by_username(usuario):
        errors.append("El usuario ya está registrado.")
    if get_user_by_email(email):
        errors.append("El email ya está registrado.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "admin/usuario_nuevo.html",
            usuario=usuario,
            email=email,
            nombre=nombre,
            ciudad=ciudad,
            provincia=provincia,
            pais=pais,
            notas=notas,
            is_admin=is_admin,
        ), 400

    create_user(
        usuario=usuario,
        email=email,
        password_hash=hash_password(password),
        nombre=nombre,
        ciudad=ciudad,
        provincia=provincia,
        pais=pais,
        notas=notas,
        is_admin=is_admin,
    )
    flash("Usuario creado correctamente.", "success")
    return redirect(url_for("admin.list_users_view"))


@bp.route("/usuarios/<int:user_id>/reset-password", methods=["POST"])
@require_admin
def reset_password(user_id):
    password = request.form.get("password") or ""
    error = validate_password(password)
    if error:
        flash(error, "danger")
        return redirect(url_for("admin.list_users_view"))

    user = get_user_by_id(user_id)
    if user is None:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("admin.list_users_view"))

    update_user_password(user_id, hash_password(password))
    flash("Contraseña actualizada correctamente.", "success")
    return redirect(url_for("admin.list_users_view"))
