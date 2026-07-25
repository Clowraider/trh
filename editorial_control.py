import logging

import publicador

from prompt_loader import load_json_file, load_prompt_text


logger = logging.getLogger(__name__)


def validate_editorial_control_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise ValueError("Editorial control rules must be a non-empty list")

    normalized_rules = []
    seen_codes = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Editorial control rules must contain objects")

        code = rule.get("code")
        instruction = rule.get("instruction")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Editorial control rule code must be a non-empty string")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(
                "Editorial control rule instruction must be a non-empty string"
            )

        normalized_code = code.strip()
        if normalized_code in seen_codes:
            raise ValueError("Editorial control rule codes must be unique")

        seen_codes.add(normalized_code)
        normalized_rules.append(
            {
                "code": normalized_code,
                "instruction": instruction.strip(),
            }
        )

    return normalized_rules


EDITORIAL_CONTROL_RULES = load_json_file(
    "EDITORIAL_CONTROL_RULES_FILE",
    logger,
    validator=validate_editorial_control_rules,
)

EDITORIAL_CONTROL_SYSTEM_PROMPT = load_prompt_text(
    "EDITORIAL_CONTROL_SYSTEM_PROMPT_FILE",
    logger,
)


def _rules_block():
    return "\n".join(
        f"- {rule['code']}: {rule['instruction']}" for rule in EDITORIAL_CONTROL_RULES
    )


def build_editorial_control_prompt(contenido):
    return "\n".join(
        [
            "Reglas editoriales a controlar:",
            _rules_block(),
            "",
            "Artículo a revisar:",
            f"TÍTULO: {contenido.get('titulo', '')}",
            f"RESUMEN: {contenido.get('resumen', '')}",
            f"ARTÍCULO: {contenido.get('articulo', '')}",
        ]
    )


def validate_editorial_control_result(result):
    if not isinstance(result, dict):
        raise ValueError("Control editorial inválido")

    passed = result.get("passed")
    issues = result.get("issues")
    instructions = result.get("correction_instructions")

    if not isinstance(passed, bool):
        raise ValueError("Control editorial inválido")
    if not isinstance(issues, list) or any(not isinstance(item, str) for item in issues):
        raise ValueError("Control editorial inválido")
    if not isinstance(instructions, str):
        raise ValueError("Control editorial inválido")

    allowed_codes = {rule["code"] for rule in EDITORIAL_CONTROL_RULES}
    if any(item not in allowed_codes for item in issues):
        raise ValueError("Control editorial inválido")

    normalized = {
        "passed": passed,
        "issues": issues,
        "correction_instructions": instructions.strip(),
    }
    if not normalized["passed"] and not normalized["correction_instructions"]:
        normalized["correction_instructions"] = (
            "Corregí los problemas editoriales detectados y volvé a redactar con tono neutral."
        )
    return normalized


def review_article(contenido, ai_client=None):
    client = ai_client or publicador.llamar_ia_json
    result = client(
        build_editorial_control_prompt(contenido),
        system_prompt=EDITORIAL_CONTROL_SYSTEM_PROMPT,
        max_tokens=600,
        temperature=0,
        title="TRH Editorial Control",
    )
    return validate_editorial_control_result(result)


def _build_regeneration_note(original_note, correction_instructions):
    parts = []
    cleaned_original = (original_note or "").strip()
    cleaned_corrections = (correction_instructions or "").strip()
    if cleaned_original:
        parts.append(cleaned_original)
    if cleaned_corrections:
        parts.append(
            "AJUSTES DE CONTROL EDITORIAL OBLIGATORIOS:\n"
            f"{cleaned_corrections}"
        )
    return "\n\n".join(parts)


def _build_review_required_result(result, attempts, message, review=None):
    editorial_control = {
        "attempts": attempts,
        "review_required": True,
        "error": message,
    }
    if review is not None:
        editorial_control["initial_review"] = review
    return {
        **result,
        "editorial_control": editorial_control,
    }


def generate_article_with_editorial_control(
    cluster_id,
    nota_ia="",
    generator=None,
    review_article=review_article,
    set_review_required=None,
):
    article_generator = generator or publicador.generar_articulo_para_cluster
    set_flag = set_review_required or publicador.set_requiere_revision_editorial

    first_result = article_generator(cluster_id, nota_ia=nota_ia)
    if not first_result.get("ok"):
        return first_result

    try:
        first_review = review_article(first_result["contenido"])
    except Exception as exc:
        logger.warning("editorial_control.review_failed cluster_id=%s", cluster_id)
        set_flag(cluster_id, True)
        return _build_review_required_result(
            first_result,
            attempts=1,
            message=f"Error de control editorial: {exc}",
        )

    if first_review["passed"]:
        set_flag(cluster_id, False)
        return {
            **first_result,
            "editorial_control": {
                "attempts": 1,
                "review_required": False,
                "final_review": first_review,
            },
        }

    second_result = article_generator(
        cluster_id,
        nota_ia=_build_regeneration_note(
            nota_ia,
            first_review["correction_instructions"],
        ),
    )
    if not second_result.get("ok"):
        return second_result

    try:
        second_review = review_article(second_result["contenido"])
    except Exception as exc:
        logger.warning("editorial_control.review_failed cluster_id=%s retry=1", cluster_id)
        set_flag(cluster_id, True)
        return _build_review_required_result(
            second_result,
            attempts=2,
            message=f"Error de control editorial: {exc}",
            review=first_review,
        )

    review_required = not second_review["passed"]
    set_flag(cluster_id, review_required)
    return {
        **second_result,
        "editorial_control": {
            "attempts": 2,
            "review_required": review_required,
            "initial_review": first_review,
            "final_review": second_review,
        },
    }
