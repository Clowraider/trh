import editorial_control as control


def article(title="Título"):
    return {
        "titulo": title,
        "resumen": "Resumen",
        "articulo": "Cuerpo",
        "categoria": "Sociedad",
    }


def test_control_passes_on_first_review_without_regeneration():
    generator_calls = []
    review_calls = []
    review_flags = []

    def generate(cluster_id, nota_ia=""):
        generator_calls.append((cluster_id, nota_ia))
        return {"ok": True, "contenido": article()}

    def review(_contenido):
        review_calls.append(True)
        return {
            "passed": True,
            "issues": [],
            "correction_instructions": "",
        }

    result = control.generate_article_with_editorial_control(
        7,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 1
    assert result["editorial_control"]["review_required"] is False
    assert generator_calls == [(7, "nota original")]
    assert review_calls == [True]
    assert review_flags == [(7, False)]


def test_control_regenerates_once_with_correction_instructions_and_then_passes():
    generator_calls = []
    review_flags = []
    generated_articles = [article("Primera"), article("Segunda")]
    review_results = [
        {
            "passed": False,
            "issues": ["mentions_other_media"],
            "correction_instructions": "Reescribí sin nombrar otros medios y mantené un tono neutral.",
        },
        {
            "passed": True,
            "issues": [],
            "correction_instructions": "",
        },
    ]

    def generate(cluster_id, nota_ia=""):
        generator_calls.append((cluster_id, nota_ia))
        return {"ok": True, "contenido": generated_articles.pop(0)}

    def review(_contenido):
        return review_results.pop(0)

    result = control.generate_article_with_editorial_control(
        8,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result["ok"] is True
    assert result["contenido"]["titulo"] == "Segunda"
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is False
    assert generator_calls[0] == (8, "nota original")
    assert generator_calls[1][0] == 8
    assert "nota original" in generator_calls[1][1]
    assert "Reescribí sin nombrar otros medios" in generator_calls[1][1]
    assert review_flags == [(8, False)]


def test_control_marks_cluster_for_editorial_review_after_second_failure():
    review_flags = []

    def generate(_cluster_id, nota_ia=""):
        return {"ok": True, "contenido": article(nota_ia or "Versión")}

    def review(_contenido):
        return {
            "passed": False,
            "issues": ["accusatory_tone"],
            "correction_instructions": "Bajá el tono acusatorio y sostené solo hechos verificados.",
        }

    result = control.generate_article_with_editorial_control(
        9,
        nota_ia="",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["final_review"]["passed"] is False
    assert review_flags == [(9, True)]


def test_control_marks_review_required_when_first_review_errors_after_generation():
    review_flags = []

    def generate(_cluster_id, nota_ia=""):
        return {"ok": True, "contenido": article(nota_ia or "Versión")}

    def review(_contenido):
        raise RuntimeError("control caído")

    result = control.generate_article_with_editorial_control(
        10,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 1
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["error"] == "Error de control editorial: control caído"
    assert review_flags == [(10, True)]


def test_control_marks_review_required_when_second_review_errors_after_regeneration():
    review_flags = []
    generated_articles = [article("Primera"), article("Segunda")]
    review_results = [
        {
            "passed": False,
            "issues": ["accusatory_tone"],
            "correction_instructions": "Bajá el tono acusatorio.",
        },
        RuntimeError("control caído en retry"),
    ]

    def generate(_cluster_id, nota_ia=""):
        return {"ok": True, "contenido": generated_articles.pop(0)}

    def review(_contenido):
        outcome = review_results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    result = control.generate_article_with_editorial_control(
        11,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result["ok"] is True
    assert result["contenido"]["titulo"] == "Segunda"
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["error"] == "Error de control editorial: control caído en retry"
    assert result["editorial_control"]["initial_review"]["passed"] is False
    assert review_flags == [(11, True)]


def test_control_marks_review_required_when_regeneration_fails_after_rejected_review():
    review_flags = []

    def generate(_cluster_id, nota_ia=""):
        if "AJUSTES DE CONTROL EDITORIAL OBLIGATORIOS" in nota_ia:
            return {"ok": False, "error": "falló la regeneración"}
        return {"ok": True, "contenido": article("Primera")}

    def review(_contenido):
        return {
            "passed": False,
            "issues": ["accusatory_tone"],
            "correction_instructions": "Bajá el tono acusatorio.",
        }

    result = control.generate_article_with_editorial_control(
        12,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=lambda cluster_id, value: review_flags.append((cluster_id, value)),
    )

    assert result == {"ok": False, "error": "falló la regeneración"}
    assert review_flags == [(12, True)]
