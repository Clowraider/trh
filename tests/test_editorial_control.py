from trh.editorial import editorial_control as control


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

    def generate(cluster_id, nota_ia="", user_id=None):
        generator_calls.append((cluster_id, nota_ia, user_id))
        return {"ok": True, "contenido": article()}

    def review(_contenido):
        review_calls.append(True)
        return {
            "passed": True,
            "issues": [],
            "correction_instructions": "",
        }

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        7,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 1
    assert result["editorial_control"]["review_required"] is False
    assert generator_calls == [(7, "nota original", None)]
    assert review_calls == [True]
    assert review_flags == [(7, False, None)]


def test_control_regenerates_once_with_correction_instructions_and_then_passes():
    generator_calls = []
    review_flags = []
    generated_articles = [article("Primera"), article("Segunda")]
    review_results = [
        {
            "passed": False,
            "issues": ["unnecessary_source_or_media_mentions"],
            "correction_instructions": "Reescribí sin nombrar otros medios y mantené un tono neutral.",
        },
        {
            "passed": True,
            "issues": [],
            "correction_instructions": "",
        },
    ]

    def generate(cluster_id, nota_ia="", user_id=None):
        generator_calls.append((cluster_id, nota_ia, user_id))
        return {"ok": True, "contenido": generated_articles.pop(0)}

    def review(_contenido):
        return review_results.pop(0)

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        8,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result["ok"] is True
    assert result["contenido"]["titulo"] == "Segunda"
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is False
    assert generator_calls[0] == (8, "nota original", None)
    assert generator_calls[1][0] == 8
    assert "nota original" in generator_calls[1][1]
    assert "Reescribí sin nombrar otros medios" in generator_calls[1][1]
    assert review_flags == [(8, False, None)]


def test_control_marks_cluster_for_editorial_review_after_second_failure():
    review_flags = []

    def generate(_cluster_id, nota_ia="", user_id=None):
        return {"ok": True, "contenido": article(nota_ia or "Versión")}

    def review(_contenido):
        return {
            "passed": False,
            "issues": ["unsupported_accusations"],
            "correction_instructions": "Bajá el tono acusatorio y sostené solo hechos verificados.",
        }

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        9,
        nota_ia="",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["final_review"]["passed"] is False
    assert len(review_flags) == 1
    assert review_flags[0][0] == 9
    assert review_flags[0][1] is True
    assert review_flags[0][2] is not None
    assert "NO PASÓ" in review_flags[0][2]
    assert "unsupported_accusations" in review_flags[0][2]


def test_control_marks_review_required_when_first_review_errors_after_generation():
    review_flags = []

    def generate(_cluster_id, nota_ia="", user_id=None):
        return {"ok": True, "contenido": article(nota_ia or "Versión")}

    def review(_contenido):
        raise RuntimeError("control caído")

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        10,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result["ok"] is True
    assert result["editorial_control"]["attempts"] == 1
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["error"] == "Error de control editorial: control caído"
    assert len(review_flags) == 1
    assert review_flags[0][0] == 10
    assert review_flags[0][1] is True
    assert review_flags[0][2] is not None
    assert "Error: control caído" in review_flags[0][2]


def test_control_marks_review_required_when_second_review_errors_after_regeneration():
    review_flags = []
    generated_articles = [article("Primera"), article("Segunda")]
    review_results = [
        {
            "passed": False,
            "issues": ["unsupported_accusations"],
            "correction_instructions": "Bajá el tono acusatorio.",
        },
        RuntimeError("control caído en retry"),
    ]

    def generate(_cluster_id, nota_ia="", user_id=None):
        return {"ok": True, "contenido": generated_articles.pop(0)}

    def review(_contenido):
        outcome = review_results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        11,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result["ok"] is True
    assert result["contenido"]["titulo"] == "Segunda"
    assert result["editorial_control"]["attempts"] == 2
    assert result["editorial_control"]["review_required"] is True
    assert result["editorial_control"]["error"] == "Error de control editorial: control caído en retry"
    assert result["editorial_control"]["initial_review"]["passed"] is False
    assert len(review_flags) == 1
    assert review_flags[0][0] == 11
    assert review_flags[0][1] is True
    assert review_flags[0][2] is not None
    assert "Error: control caído en retry" in review_flags[0][2]


def test_control_marks_review_required_when_regeneration_fails_after_rejected_review():
    review_flags = []

    def generate(_cluster_id, nota_ia="", user_id=None):
        if "AJUSTES DE CONTROL EDITORIAL OBLIGATORIOS" in nota_ia:
            return {"ok": False, "error": "falló la regeneración"}
        return {"ok": True, "contenido": article("Primera")}

    def review(_contenido):
        return {
            "passed": False,
            "issues": ["unsupported_accusations"],
            "correction_instructions": "Bajá el tono acusatorio.",
        }

    def set_flag(cluster_id, value, nota_editor=None, user_id=None):
        review_flags.append((cluster_id, value, nota_editor))

    result = control.generate_article_with_editorial_control(
        12,
        nota_ia="nota original",
        generator=generate,
        review_article=review,
        set_review_required=set_flag,
    )

    assert result == {"ok": False, "error": "falló la regeneración"}
    assert len(review_flags) == 1
    assert review_flags[0][0] == 12
    assert review_flags[0][1] is True
    assert review_flags[0][2] is None


def test_format_review_note_with_reviews():
    reviews = [
        {"passed": False, "issues": ["sesgo"], "correction_instructions": "Ser más neutral."},
        {"passed": False, "issues": ["dato_no_verificado"], "correction_instructions": "Verificar fuente."},
    ]
    note = control._format_review_note(2, reviews)
    assert "Revisión editorial requerida" in note
    assert "Intento 1: NO PASÓ" in note
    assert "Problemas: sesgo" in note
    assert "Instrucciones: Ser más neutral." in note
    assert "Intento 2: NO PASÓ" in note
    assert "Problemas: dato_no_verificado" in note


def test_format_review_note_with_error():
    note = control._format_review_note(1, [], error="La IA no respondió")
    assert "Revisión editorial requerida" in note
    assert "Error: La IA no respondió" in note
