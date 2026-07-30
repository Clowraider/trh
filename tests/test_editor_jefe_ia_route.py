import json
import re
from datetime import datetime, timezone

import pytest

from trh.editorial import editor_jefe_ia as feature


DEFAULT_MINIMUM_EDITORIAL_SCORE = "50"


def candidate(
    cluster_id=1,
    title="Cluster",
    newest_at="2026-03-06T12:00:00+00:00",
    editorial_score=8.0,
):
    return {
        "cluster_id": cluster_id, "title": title, "technical_score": 4.0,
        "editorial_score": editorial_score, "news_count": 3, "source_count": 2,
        "newest_at": newest_at, "keywords": ["economía"],
        "recent_news": [{"title": "Nota", "source": "Medio",
                         "effective_at": newest_at, "excerpt": "Contexto"}],
    }


def configure_panel(panel, **overrides):
    config = {
        "TESTING": True,
        "EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS": lambda *_: [],
        "EDITOR_JEFE_SAVE_RECOMMENDATIONS": lambda *_: None,
    }
    config.update(overrides)
    panel.app.config.update(**config)


def pop_flashes(client):
    with client.session_transaction() as session:
        flashes = list(session.get("_flashes", []))
        session["_flashes"] = []
    return flashes


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "1.5", " 1", "1 ", "true", True])
def test_maximum_rejects_non_positive_whole_numbers(raw):
    with pytest.raises(feature.FeatureError):
        feature.parse_maximum(raw)


def test_maximum_accepts_positive_whole_number_without_product_cap():
    assert feature.parse_maximum("999999") == 999999


@pytest.mark.parametrize("raw", [None, "", "0", "-1", "1.5", " 50", "50 ", "true", True])
def test_minimum_editorial_score_rejects_non_positive_whole_numbers(raw):
    with pytest.raises(feature.FeatureError):
        feature.parse_minimum_editorial_score(raw)


def test_minimum_editorial_score_accepts_positive_whole_number_without_product_cap():
    assert feature.parse_minimum_editorial_score("999999") == 999999


def test_prompt_is_compact_stable_complete_and_budgeted():
    item = candidate()
    prompt = feature.serialize_selection_payload([item], 2)
    assert prompt == json.dumps(
        {"batch_size": 2, "candidates": [item]}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )
    assert "weather and forecast items" in feature.EDITOR_JEFE_SYSTEM_PROMPT
    assert "natural Spanish" in feature.EDITOR_JEFE_SYSTEM_PROMPT
    assert "motivo breve en castellano" in feature.EDITOR_JEFE_SYSTEM_PROMPT
    base = len(feature.serialize_selection_payload([candidate(title="")], 1).encode())
    assert len(feature.serialize_selection_payload(
        [candidate(title="x" * (48_000 - base))], 1).encode()) == 48_000
    with pytest.raises(feature.FeatureError):
        feature.serialize_selection_payload(
            [candidate(title="x" * (48_001 - base))], 1
        )


def test_requested_number_limits_total_input_and_splits_batches_of_five():
    candidates = [candidate(cluster_id=index) for index in range(12)]
    payloads = []

    class Client:
        def select(self, payload):
            payloads.append(json.loads(payload))
            cluster_id = payloads[-1]["candidates"][-1]["cluster_id"]
            return {"selections": [{"cluster_id": cluster_id, "reason": f"Relevant {cluster_id}"}]}

    result = feature.select_recommendations(candidates, 7, Client())

    assert [[item["cluster_id"] for item in payload["candidates"]] for payload in payloads] == [
        list(range(5)),
        [5, 6],
    ]
    assert [payload["batch_size"] for payload in payloads] == [5, 2]
    assert [item["cluster_id"] for item in result.selections] == [4, 6]
    assert [item["reason"] for item in result.selections] == ["Relevant 4", "Relevant 6"]
    assert (result.total_batches, result.failed_batches) == (2, 0)


@pytest.mark.parametrize("requested_number", [10, 15])
def test_all_batches_pass_for_large_requested_numbers(requested_number):
    candidates = [candidate(cluster_id=index) for index in range(requested_number + 2)]
    payloads = []

    class Client:
        def select(self, payload):
            parsed = json.loads(payload)
            payloads.append(parsed)
            return {"selections": [{
                "cluster_id": parsed["candidates"][0]["cluster_id"],
                "reason": "Relevant",
            }]}

    result = feature.select_recommendations(candidates, requested_number, Client())

    assert len(payloads) == requested_number // 5
    assert all(len(payload["candidates"]) == 5 for payload in payloads)
    assert [item["cluster_id"] for item in result.selections] == list(
        range(0, requested_number, 5)
    )
    assert (result.total_batches, result.failed_batches) == (
        requested_number // 5,
        0,
    )


def test_failed_middle_batch_preserves_earlier_and_later_successes(caplog):
    candidates = [candidate(cluster_id=index) for index in range(15)]
    calls = 0

    class Client:
        def select(self, payload):
            nonlocal calls
            calls += 1
            parsed = json.loads(payload)
            if calls == 2:
                raise feature.FeatureError("sensitive provider detail", "provider_failure")
            cluster_id = parsed["candidates"][0]["cluster_id"]
            return {"selections": [{"cluster_id": cluster_id, "reason": "Relevant"}]}

    with caplog.at_level("INFO", logger=feature.__name__):
        result = feature.select_recommendations(candidates, 15, Client())

    assert calls == 3
    assert [item["cluster_id"] for item in result.selections] == [0, 10]
    assert (result.total_batches, result.failed_batches) == (3, 1)
    assert "batch_index=2 batch_count=3 batch_size=5" in caplog.text
    assert "sensitive provider detail" not in caplog.text


def test_all_failed_batches_return_failure_metadata_not_zero():
    candidates = [candidate(cluster_id=index) for index in range(10)]

    class Client:
        def select(self, _payload):
            raise feature.FeatureError("provider failed", "provider_failure")

    result = feature.select_recommendations(candidates, 10, Client())

    assert result.selections == []
    assert (result.total_batches, result.failed_batches) == (2, 2)


def test_missing_provider_configuration_fails_fast_across_batches(caplog):
    post_calls = []
    client = feature.OpenRouterSelectionClient(
        post=lambda *_args, **_kwargs: post_calls.append("called"),
        api_key="",
        models=("safe-model",),
    )

    with caplog.at_level("WARNING", logger=feature.__name__):
        result = feature.select_recommendations(
            [candidate(cluster_id=index) for index in range(15)],
            15,
            client,
        )

    assert post_calls == []
    assert result.selections == []
    assert (result.total_batches, result.failed_batches) == (3, 3)
    assert caplog.text.count("provider_configuration_failure") == 1
    assert "model=safe-model error_category=configuration http_status=none" in caplog.text


@pytest.mark.parametrize("body", [
    None, [], {}, {"selections": [], "extra": 1},
    {"selections": [{}]}, {"selections": [{"cluster_id": True, "reason": "ok"}]},
    {"selections": [{"cluster_id": "1", "reason": "ok"}]},
    {"selections": [{"cluster_id": 9, "reason": "ok"}]},
    {"selections": [{"cluster_id": 1, "reason": "ok"}, {"cluster_id": 1, "reason": "again"}]},
    {"selections": [{"cluster_id": 1, "reason": " "}]},
    {"selections": [{"cluster_id": 1, "reason": "bad\nreason"}]},
    {"selections": [{"cluster_id": 1, "reason": "x" * 241}]},
])
def test_validation_fails_closed(body):
    with pytest.raises(feature.FeatureError):
        feature.validate_selection_response(body, [candidate()], 1)


def test_validation_enforces_ceiling_and_restores_server_order():
    candidates = [candidate(2, newest_at="2026-03-06T13:00:00+00:00"), candidate(1)]
    body = {"selections": [{"cluster_id": 1, "reason": " second "},
                            {"cluster_id": 2, "reason": "first"}]}
    with pytest.raises(feature.FeatureError):
        feature.validate_selection_response(body, candidates, 1)
    result = feature.validate_selection_response(body, candidates, 2)
    assert [item["cluster_id"] for item in result] == [2, 1]
    assert result[1]["reason"] == "second"


def test_openrouter_client_uses_publicador_transport_policy():
    calls = []

    class Response:
        status_code = 200
        def raise_for_status(self):
            calls.append("raise_for_status")
        def json(self):
            return {"choices": [{"message": {"content": '{"selections":[]}'}}]}

    def post(url, **kwargs):
        calls.append((url, kwargs)); return Response()

    client = feature.OpenRouterSelectionClient(
        post=post, api_key="secret", models=("one", "two"), sleep=lambda _: None
    )
    assert client.select("{}") == {"selections": []}
    request = calls[0][1]["json"]
    headers = calls[0][1]["headers"]
    assert request["model"] == "one"
    assert request["messages"][0]["content"] == feature.EDITOR_JEFE_SYSTEM_PROMPT
    assert request["max_tokens"] == 1200
    assert request["response_format"] == {"type": "json_object"}
    assert calls[0][1]["timeout"] == 70
    assert headers == {
        "Authorization": "Bearer secret", "Content-Type": "application/json",
        "HTTP-Referer": "https://trh.local", "X-Title": "TRH Editor Jefe IA",
    }
    assert calls[-1] == "raise_for_status"


def test_openrouter_skips_to_next_model_after_429_without_retry():
    calls, sleeps = [], []

    class Response:
        def __init__(self, status_code, content=None):
            self.status_code, self.content = status_code, content
        def raise_for_status(self):
            if self.status_code >= 400:
                raise feature.requests.HTTPError(str(self.status_code))
        def json(self):
            return {"choices": [{"message": {"content": self.content}}]}

    outcomes = [Response(429), Response(200, '{"selections":[]}')]
    def post(_url, **kwargs):
        calls.append(kwargs["json"]["model"])
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = feature.OpenRouterSelectionClient(
        post=post, api_key="secret", models=("one", "two"), sleep=sleeps.append
    )
    assert client.select("{}") == {"selections": []}
    assert calls == ["one", "two"]
    assert sleeps == []


def test_openrouter_falls_back_after_http_or_malformed_json():
    calls, sleeps = [], []

    class Response:
        def __init__(self, status_code=200, content=None):
            self.status_code, self.content = status_code, content
        def raise_for_status(self):
            if self.status_code >= 400:
                raise feature.requests.HTTPError(str(self.status_code))
        def json(self):
            if self.content == "malformed":
                return {"choices": [{"message": {"content": "not-json"}}]}
            return {"choices": [{"message": {"content": self.content}}]}

    outcomes = [Response(500), Response(content='{"selections":[]}')]
    def post(_url, **kwargs):
        calls.append(kwargs["json"]["model"])
        return outcomes.pop(0)

    client = feature.OpenRouterSelectionClient(
        post=post, api_key="secret", models=("one", "two"), sleep=sleeps.append
    )
    assert client.select("{}") == {"selections": []}
    assert calls == ["one", "two"]
    assert sleeps == []


def test_provider_and_validation_logs_are_structured_and_secret_safe(caplog):
    secret = "api-key-never-log"
    raw_response = "raw-model-response-never-log"

    class Response:
        status_code = 503

        def raise_for_status(self):
            error = feature.requests.HTTPError("provider exception secret")
            error.response = self
            raise error

        def json(self):
            return {"raw": raw_response}

    client = feature.OpenRouterSelectionClient(
        post=lambda *_args, **_kwargs: Response(),
        api_key=secret,
        models=("safe-model",),
    )
    with caplog.at_level("WARNING", logger=feature.__name__):
        with pytest.raises(feature.FeatureError):
            client.select('{"prompt":"payload-never-log"}')
        with pytest.raises(feature.FeatureError):
            feature.validate_selection_response(
                {"selections": [{"cluster_id": 999, "reason": "unknown"}]},
                [candidate()],
                1,
            )

    assert "model=safe-model error_category=http_error http_status=503" in caplog.text
    assert "validation_failure reason=cluster_id" in caplog.text
    for forbidden in (secret, raw_response, "provider exception secret", "payload-never-log"):
        assert forbidden not in caplog.text


@pytest.mark.parametrize(("reason", "expected_category", "sensitive_content"), [
    ("   ", "reason_empty", "selections"),
    ("sensitive-too-long-" + "x" * 240, "reason_too_long", "sensitive-too-long"),
    (
        "sensitive-control\x00character",
        "reason_control_character",
        "sensitive-control",
    ),
])
def test_invalid_reason_logs_exact_safe_category_without_content(
    caplog, reason, expected_category, sensitive_content
):
    body = {"selections": [{"cluster_id": 1, "reason": reason}]}

    with caplog.at_level("WARNING", logger=feature.__name__):
        with pytest.raises(feature.FeatureError):
            feature.validate_selection_response(body, [candidate()], 1)

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        f"editor_jefe.validation_failure reason={expected_category}"
    ]
    assert sensitive_content not in caplog.text
    assert reason not in caplog.text


def test_openrouter_missing_choice_fails_as_generic_feature_error():
    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"choices": []}
    client = feature.OpenRouterSelectionClient(
        post=lambda *args, **kwargs: Response(), api_key="secret", models=("one",),
        sleep=lambda _: None,
    )
    with pytest.raises(feature.FeatureError):
        client.select("{}")


def test_get_and_post_show_and_persist_saved_recommendations(monkeypatch):
    import app as panel
    calls = []
    candidates = [{**candidate(editorial_score=80), "keywords": ["economía", "Otra"]}]
    saved = []

    def builder(factory, keyword_loader):
        calls.append((factory, keyword_loader)); return candidates

    def load_saved(_factory):
        return list(saved)

    def save_saved(_factory, selections):
        saved.extend(selections)

    class Client:
        def select(self, payload):
            return {"selections": [{"cluster_id": 1, "reason": "Relevant"}]}

    factory = object()
    monkeypatch.setattr(
        panel,
        "listar_keywords_prioridad_activas",
        lambda: [{"keyword": " ECONOMÍA ", "activo": True}],
    )
    configure_panel(panel, EDITOR_JEFE_CONNECTION_FACTORY=factory,
                    EDITOR_JEFE_CONTEXT_BUILDER=builder,
                    EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
                    EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=load_saved,
                    EDITOR_JEFE_SAVE_RECOMMENDATIONS=save_saved)
    client = panel.app.test_client()
    get_response = client.get("/editor-jefe-ia")
    assert get_response.status_code == 200 and calls == []
    assert f'value="{DEFAULT_MINIMUM_EDITORIAL_SCORE}"'.encode() in get_response.data
    assert b"Propuestas guardadas" not in get_response.data
    response = client.post(
        "/editor-jefe-ia",
        data={"maximum": "1", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert "no-store" in get_response.headers["Cache-Control"]
    assert calls == [(factory, panel.obtener_keywords_por_clusters_ids)]
    assert b"Relevant" in response.data and b"guardadas" in response.data
    assert b"Descartar" in response.data
    assert b"return_to" in response.data
    assert b"/descartar/1" in response.data
    assert b"Propuestas guardadas" in response.data
    html = response.get_data(as_text=True)
    assert html.count('data-priority-keyword="true"') == 2
    assert html.count('data-priority-keyword="false"') == 2
    assert re.search(r'Nuevas recomendaciones[\s\S]*data-priority-keyword="true"[\s\S]*>\s*economía\s*<', html)
    assert re.search(r'Propuestas guardadas[\s\S]*data-priority-keyword="false"[\s\S]*>\s*Otra\s*<', html)
    assert "Location" not in response.headers
    assert response.headers.getlist("Set-Cookie") == []
    followup_get = client.get("/editor-jefe-ia")
    assert b"Relevant" in followup_get.data
    assert b"Propuestas guardadas" in followup_get.data


@pytest.mark.parametrize("maximum", ["abc", "1.5", "0", "-1"])
def test_invalid_maximum_explains_positive_whole_number_without_dependencies(maximum):
    import app as panel

    calls = []
    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: calls.append("context"),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: calls.append("provider"),
    )
    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": maximum, "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert response.status_code == 200
    assert b"n\xc3\xbamero entero positivo" in response.data
    assert calls == []
    assert b"Recomendaci" not in response.data
    assert "Location" not in response.headers
    assert response.headers.getlist("Set-Cookie") == []
    assert "no-store" in response.headers["Cache-Control"]


def test_invalid_minimum_score_explains_positive_whole_number_without_dependencies():
    import app as panel

    calls = []
    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: calls.append("context"),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: calls.append("provider"),
    )
    response = panel.app.test_client().post(
        "/editor-jefe-ia", data={"maximum": "1", "minimum_editorial_score": "0"}
    )
    assert response.status_code == 200
    assert b"score editorial" in response.data
    assert calls == []
    assert b"Recomendaci" not in response.data


def test_capacity_error_tells_user_to_request_fewer_candidates():
    import app as panel

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: [candidate(title="x" * 48_000, editorial_score=99)],
    )
    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "1", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert b"Uno de los lotes solicitados es demasiado grande" in response.data
    assert b"Prob\xc3\xa1 con menos candidatos" in response.data
    assert b"No se hizo ninguna solicitud a la IA" not in response.data
    assert b"ped\xc3\xad menos candidatos" not in response.data
    assert b"too many eligible clusters" not in response.data
    assert b"try again later" not in response.data


def test_provider_and_response_failures_render_only_retryable_error():
    import app as panel

    class BrokenClient:
        def select(self, payload):
            raise feature.FeatureError("provider detail")

    class InvalidClient:
        def select(self, payload):
            return {"selections": [{"cluster_id": 999, "reason": "unknown"}]}

    configure_panel(panel, EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: [candidate(editorial_score=80)],
                    EDITOR_JEFE_CONNECTION_FACTORY=object())
    for provider in (lambda: BrokenClient(), lambda: InvalidClient()):
        panel.app.config["EDITOR_JEFE_CLIENT_FACTORY"] = provider
        response = panel.app.test_client().post(
            "/editor-jefe-ia",
            data={"maximum": "1", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
        )
        assert response.status_code == 200
        assert b"Prob\xc3\xa1 de nuevo" in response.data
        assert b"provider detail" not in response.data and b"unknown" not in response.data
        assert b"Recomendaci" not in response.data


def test_threshold_filters_candidates_before_provider_call(monkeypatch):
    import app as panel

    payloads = []
    candidates = [
        candidate(cluster_id=1, title="Bajo", editorial_score=50),
        candidate(cluster_id=2, title="Alto", editorial_score=51),
        candidate(cluster_id=3, title="Muy alto", editorial_score=80),
    ]

    class Client:
        def select(self, payload):
            payloads.append(json.loads(payload))
            return {"selections": [{"cluster_id": 2, "reason": "Relevant"}]}

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: candidates,
        EDITOR_JEFE_CONNECTION_FACTORY=object(),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
    )
    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "5", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert response.status_code == 200
    assert [item["cluster_id"] for item in payloads[0]["candidates"]] == [1, 2, 3]
    assert b"Relevant" in response.data


def test_saved_recommendations_are_excluded_and_new_ones_are_accumulated():
    import app as panel

    payloads = []
    saved = [{**candidate(cluster_id=1, title="Viejo", editorial_score=90), "reason": "Saved"}]
    candidates = [
        candidate(cluster_id=1, title="Viejo", editorial_score=90),
        candidate(cluster_id=2, title="Nuevo", editorial_score=80),
        candidate(cluster_id=3, title="Otro", editorial_score=70),
    ]

    def load_saved(_factory):
        return list(saved)

    def save_saved(_factory, selections):
        saved.extend(selections)

    class Client:
        def select(self, payload):
            payloads.append(json.loads(payload))
            return {"selections": [{"cluster_id": 2, "reason": "Fresh"}]}

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: candidates,
        EDITOR_JEFE_CONNECTION_FACTORY=object(),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=load_saved,
        EDITOR_JEFE_SAVE_RECOMMENDATIONS=save_saved,
    )
    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "5", "minimum_editorial_score": "60"},
    )
    assert response.status_code == 200
    assert [item["cluster_id"] for item in payloads[0]["candidates"]] == [2, 3]
    assert [item["cluster_id"] for item in saved] == [1, 2]
    assert b"Viejo" in response.data
    assert b"Fresh" in response.data


def test_route_batches_requested_candidates_in_groups_of_five_and_keeps_total_cap():
    import app as panel

    payloads = []
    saved = []
    candidates = [candidate(cluster_id=index, title=f"Cluster {index}", editorial_score=80)
                  for index in range(1, 10)]

    def load_saved(_factory):
        return list(saved)

    def save_saved(_factory, selections):
        saved.extend(selections)

    class Client:
        def select(self, payload):
            parsed = json.loads(payload)
            payloads.append(parsed)
            return {
                "selections": [{
                    "cluster_id": parsed["candidates"][-1]["cluster_id"],
                    "reason": f"Batch {len(payloads)}",
                }]
            }

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: candidates,
        EDITOR_JEFE_CONNECTION_FACTORY=object(),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=load_saved,
        EDITOR_JEFE_SAVE_RECOMMENDATIONS=save_saved,
    )

    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "7", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )

    assert response.status_code == 200
    assert [[item["cluster_id"] for item in payload["candidates"]] for payload in payloads] == [
        [1, 2, 3, 4, 5],
        [6, 7],
    ]
    assert [payload["batch_size"] for payload in payloads] == [5, 2]
    assert [item["cluster_id"] for item in saved] == [5, 7]
    assert b"Batch 1" in response.data
    assert b"Batch 2" in response.data
    assert b"Cluster 8" not in response.data


def test_route_saves_and_displays_partial_batch_results_with_warning():
    import app as panel

    saved = []
    calls = 0
    candidates = [candidate(cluster_id=index, editorial_score=80) for index in range(15)]

    class Client:
        def select(self, payload):
            nonlocal calls
            calls += 1
            parsed = json.loads(payload)
            if calls == 2:
                raise feature.FeatureError("private detail", "validation_failure")
            cluster_id = parsed["candidates"][0]["cluster_id"]
            return {"selections": [{
                "cluster_id": cluster_id,
                "reason": f"Success {cluster_id}",
            }]}

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: candidates,
        EDITOR_JEFE_CONNECTION_FACTORY=object(),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
        EDITOR_JEFE_SAVE_RECOMMENDATIONS=lambda _factory, selections: saved.extend(selections),
    )

    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "15", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )

    assert response.status_code == 200
    assert calls == 3
    assert [item["cluster_id"] for item in saved] == [0, 10]
    assert b"Success 0" in response.data and b"Success 10" in response.data
    assert b"resultado parcial" in response.data


def test_route_renders_retryable_error_when_all_attempted_batches_fail():
    import app as panel

    saved = []
    candidates = [candidate(cluster_id=index, editorial_score=80) for index in range(10)]

    class Client:
        def select(self, _payload):
            raise feature.FeatureError("private detail", "provider_failure")

    configure_panel(
        panel,
        EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: candidates,
        EDITOR_JEFE_CONNECTION_FACTORY=object(),
        EDITOR_JEFE_CLIENT_FACTORY=lambda: Client(),
        EDITOR_JEFE_SAVE_RECOMMENDATIONS=lambda _factory, selections: saved.extend(selections),
    )

    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "10", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )

    assert b"No se pudo completar la recomendaci" in response.data
    assert b"resultado v\xc3\xa1lido" not in response.data
    assert saved == []


def test_single_cluster_generation_route_updates_note_and_reuses_generator(monkeypatch):
    import app as panel

    configure_panel(panel)
    client = panel.app.test_client()
    updates = []
    generator_calls = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "pendiente",
            "nota_ia": "nota previa",
        },
    )
    monkeypatch.setattr(
        panel,
        "_update_cluster_nota_ia",
        lambda cluster_id, nota_ia: updates.append((cluster_id, nota_ia)),
    )
    panel.app.config["EDITOR_JEFE_ARTICLE_GENERATOR"] = (
        lambda cluster_id, nota_ia="": generator_calls.append((cluster_id, nota_ia))
        or {"ok": True}
    )

    response = client.post("/generar/7", data={"nota_ia": "  nueva nota  "})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert updates == [(7, "nueva nota")]
    assert generator_calls == [(7, "nueva nota")]
    assert pop_flashes(client) == [("success", "✅ Artículo generado correctamente")]


def test_single_cluster_generation_route_blocks_invalid_states_without_calling_generator(monkeypatch):
    import app as panel

    configure_panel(panel)
    client = panel.app.test_client()
    generator_calls = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "publicado",
            "nota_ia": "",
        },
    )
    panel.app.config["EDITOR_JEFE_ARTICLE_GENERATOR"] = (
        lambda cluster_id, nota_ia="": generator_calls.append((cluster_id, nota_ia))
        or {"ok": True}
    )

    response = client.post("/generar/8", data={"nota_ia": "ignorada"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/8")
    assert generator_calls == []
    assert pop_flashes(client) == [
        ("warning", "No se puede generar/regenerar: estado actual = 'publicado'")
    ]


def test_single_cluster_generation_route_converts_generator_exception_into_flash(monkeypatch):
    import app as panel

    configure_panel(panel)
    client = panel.app.test_client()

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "pendiente",
            "nota_ia": "",
        },
    )

    def explode(_cluster_id, nota_ia=""):
        raise RuntimeError(f"boom: {nota_ia}")

    panel.app.config["EDITOR_JEFE_ARTICLE_GENERATOR"] = explode

    response = client.post("/generar/9", data={"nota_ia": "nota rota"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/9")
    assert pop_flashes(client) == [("danger", "❌ Error: boom: nota rota")]


def test_saved_recommendations_bulk_generate_button_is_shown_only_with_saved_items():
    import app as panel

    configure_panel(panel)
    client = panel.app.test_client()

    empty_response = client.get("/editor-jefe-ia")
    assert b"Generar art\xc3\xadculos IA" not in empty_response.data
    assert b"/editor-jefe-ia/generar-guardadas" not in empty_response.data

    panel.app.config["EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS"] = lambda _factory: [
        {**candidate(cluster_id=7, title="Guardado"), "reason": "Saved"}
    ]
    saved_response = client.get("/editor-jefe-ia")
    assert b"Generar art\xc3\xadculos IA" in saved_response.data
    assert b"/editor-jefe-ia/generar-guardadas" in saved_response.data


def test_saved_recommendations_show_ready_badge_when_cluster_is_generated(monkeypatch):
    import app as panel

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=lambda _factory: [
            {
                **candidate(cluster_id=7, title="Guardado listo"),
                "reason": "Saved",
                "estado_publicacion": "pendiente",
            },
            {
                **candidate(cluster_id=8, title="Guardado pendiente"),
                "reason": "Saved too",
                "estado_publicacion": "pendiente",
            },
        ],
    )
    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "generado" if cluster_id == 7 else "pendiente",
            "foto_principal": "https://img.test/cover.jpg" if cluster_id == 7 else "",
            "fotos_secundarias": [],
            "fotos_manuales": [],
        },
    )
    monkeypatch.setattr(
        panel,
        "obtener_noticias_cluster",
        lambda cluster_id: [{"url_imagen": "https://img.test/cover.jpg", "fuente": "Medio"}] if cluster_id == 7 else [],
    )

    response = panel.app.test_client().get("/editor-jefe-ia")

    assert response.status_code == 200
    assert b"Guardado listo" in response.data
    assert b"Guardado pendiente" in response.data
    assert response.data.count("✅ Listo".encode("utf-8")) == 1


def test_saved_recommendations_show_editorial_review_badge_when_required(monkeypatch):
    import app as panel

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=lambda _factory: [
            {
                **candidate(cluster_id=7, title="Guardado con revisión"),
                "reason": "Saved",
                "estado_publicacion": "generado",
                "requiere_revision_editorial": False,
            }
        ],
    )
    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "generado",
            "requiere_revision_editorial": True,
            "foto_principal": "",
            "fotos_secundarias": [],
            "fotos_manuales": [],
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda cluster_id: [])

    response = panel.app.test_client().get("/editor-jefe-ia")

    assert response.status_code == 200
    assert b"Guardado con revisi\xc3\xb3n" in response.data
    assert "⚠️ Requiere revisión editorial".encode("utf-8") in response.data
    assert b"Elegir fotos" not in response.data
    assert b"/publicar/7" not in response.data
    assert b"Aprob\xc3\xa1 la revisi\xc3\xb3n editorial" in response.data


def test_cluster_detail_shows_editorial_review_gate_and_explicit_approval_action(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": "Cluster con revisi\xc3\xb3n",
            "estado_publicacion": "generado",
            "requiere_revision_editorial": True,
            "cantidad_noticias": 2,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": {
                "titulo": "T\xc3\xadtulo generado",
                "resumen": "Resumen generado",
                "categoria": "Policiales",
                "articulo": "<p>Texto generado</p>",
            },
            "fotos_manuales": [],
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda _cluster_id: [])

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert "⚠️ Revisión editorial obligatoria".encode("utf-8") in response.data
    assert b"Aprobar revisi\xc3\xb3n editorial" in response.data
    assert b"No se puede publicar este art\xc3\xadculo" in response.data
    assert b"/aprobar-revision-editorial/7" in response.data
    assert b"/preview/7" in response.data
    assert b"/publicar/7" not in response.data


def test_cluster_detail_exposes_revert_to_pending_action_for_generated_clusters(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": "Cluster generado",
            "estado_publicacion": "generado",
            "requiere_revision_editorial": False,
            "cantidad_noticias": 2,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": None,
            "fotos_manuales": [],
            "url_wp": None,
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda _cluster_id: [])

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert b"/revertir/7" in response.data
    assert b"Revertir a pendiente" in response.data
    assert b"/split-cluster/7" not in response.data
    assert b"Partir cluster con seleccionadas" not in response.data


def test_cluster_detail_hides_split_and_revert_actions_while_generation_is_in_flight(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": "Cluster generando",
            "estado_publicacion": "generando",
            "requiere_revision_editorial": False,
            "cantidad_noticias": 2,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": None,
            "fotos_manuales": [],
            "url_wp": None,
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda _cluster_id: [])

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert b"/revertir/7" not in response.data
    assert b"/split-cluster/7" not in response.data
    assert b"Revertir a pendiente" not in response.data
    assert b"Partir cluster con seleccionadas" not in response.data
    assert "No se puede partir ni revertir mientras la generación está en curso.".encode("utf-8") in response.data


def test_cluster_detail_hides_revert_and_split_actions_for_published_clusters(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": "Cluster publicado",
            "estado_publicacion": "publicado",
            "requiere_revision_editorial": False,
            "cantidad_noticias": 2,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": None,
            "fotos_manuales": [],
            "url_wp": "https://wp.test/7",
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda _cluster_id: [])

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert b"/revertir/7" not in response.data
    assert b"/split-cluster/7" not in response.data
    assert b"Revertir a pendiente" not in response.data
    assert b"Partir cluster con seleccionadas" not in response.data
    assert "No se puede partir ni revertir un cluster publicado.".encode("utf-8") in response.data


def test_cluster_detail_keeps_split_action_for_pending_clusters(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": "Cluster pendiente",
            "estado_publicacion": "pendiente",
            "requiere_revision_editorial": False,
            "cantidad_noticias": 2,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": None,
            "fotos_manuales": [],
            "url_wp": None,
        },
    )
    monkeypatch.setattr(
        panel,
        "obtener_noticias_cluster",
        lambda _cluster_id: [
            {
                "id": 11,
                "fuente": "Fuente",
                "titulo": "Título",
                "url_original": "https://example.com/nota",
                "url_imagen": None,
                "fecha_publicacion": None,
            }
        ],
    )

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert b"/split-cluster/7" in response.data
    assert b"Partir cluster con seleccionadas" in response.data
    assert b"/revertir/7" not in response.data


@pytest.mark.parametrize(
    ("estado_publicacion", "expected_notice"),
    [
        (
            "generando",
            "No se puede partir ni revertir mientras la generación está en curso.",
        ),
        (
            "generado",
            "Para partir este cluster, primero volvelo a pendiente.",
        ),
        (
            "publicado",
            "No se puede partir ni revertir un cluster publicado.",
        ),
    ],
)
def test_cluster_detail_keeps_source_news_visible_when_split_actions_are_blocked(
    monkeypatch, estado_publicacion, expected_notice
):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "titulo_representativo": f"Cluster {estado_publicacion}",
            "estado_publicacion": estado_publicacion,
            "requiere_revision_editorial": False,
            "cantidad_noticias": 1,
            "cantidad_fuentes": 1,
            "score": 88,
            "nota_ia": "",
            "contenido_ia": None,
            "fotos_manuales": [],
            "url_wp": "https://wp.test/7" if estado_publicacion == "publicado" else None,
        },
    )
    monkeypatch.setattr(
        panel,
        "obtener_noticias_cluster",
        lambda _cluster_id: [
            {
                "id": 11,
                "fuente": "Fuente visible",
                "titulo": "Título visible",
                "url_original": "https://example.com/nota-visible",
                "url_imagen": None,
                "fecha_publicacion": None,
            }
        ],
    )

    response = panel.app.test_client().get("/cluster/7")

    assert response.status_code == 200
    assert expected_notice.encode("utf-8") in response.data
    assert "Fuente visible".encode("utf-8") in response.data
    assert "Título visible".encode("utf-8") in response.data
    assert b"https://example.com/nota-visible" in response.data
    assert b"/split-cluster/7" not in response.data
    assert b"name=\"noticias_split\"" not in response.data


def test_generated_saved_recommendation_shows_quick_publish_controls_only_for_generated(monkeypatch):
    import app as panel

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=lambda _factory: [
            {
                **candidate(cluster_id=7, title="Guardado listo"),
                "reason": "Saved",
                "estado_publicacion": "generado",
            },
            {
                **candidate(cluster_id=8, title="Guardado pendiente"),
                "reason": "Saved too",
                "estado_publicacion": "pendiente",
            },
        ],
    )
    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "foto_principal": "https://img.test/cover.jpg" if cluster_id == 7 else "",
            "fotos_secundarias": ["https://img.test/secondary.jpg"] if cluster_id == 7 else [],
            "fotos_manuales": [],
        },
    )
    monkeypatch.setattr(
        panel,
        "obtener_noticias_cluster",
        lambda cluster_id: [
            {"url_imagen": "https://img.test/cover.jpg", "fuente": "Medio 1"},
            {"url_imagen": "https://img.test/secondary.jpg", "fuente": "Medio 2"},
        ] if cluster_id == 7 else [],
    )

    response = panel.app.test_client().get("/editor-jefe-ia")

    assert response.status_code == 200
    assert response.data.count(b"Elegir fotos") == 1
    assert b"quick-publish-7" in response.data
    assert b"/publicar/7" in response.data
    assert b"save_photos_before_publish" in response.data
    assert b"quick-publish-8" not in response.data


def test_saved_recommendations_hide_quick_publish_when_current_cluster_is_already_published(monkeypatch):
    import app as panel

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=lambda _factory: [
            {
                **candidate(cluster_id=7, title="Guardado desactualizado"),
                "reason": "Saved",
                "estado_publicacion": "generado",
                "requiere_revision_editorial": True,
            }
        ],
    )
    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "publicado",
            "requiere_revision_editorial": False,
            "foto_principal": "https://img.test/cover.jpg",
            "fotos_secundarias": ["https://img.test/secondary.jpg"],
            "fotos_manuales": [],
        },
    )
    monkeypatch.setattr(
        panel,
        "obtener_noticias_cluster",
        lambda cluster_id: [
            {"url_imagen": "https://img.test/cover.jpg", "fuente": "Medio 1"},
            {"url_imagen": "https://img.test/secondary.jpg", "fuente": "Medio 2"},
        ],
    )

    response = panel.app.test_client().get("/editor-jefe-ia")

    assert response.status_code == 200
    assert b"Guardado desactualizado" in response.data
    assert "✅ Listo".encode("utf-8") not in response.data
    assert "⚠️ Requiere revisión editorial".encode("utf-8") not in response.data
    assert b"Elegir fotos" not in response.data
    assert b"quick-publish-7" not in response.data
    assert b"/publicar/7" not in response.data


def test_editor_jefe_quick_publish_saves_selected_photos_and_redirects_to_cluster(monkeypatch):
    import app as panel

    saved_photo_selections = []
    removed = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {"id": cluster_id, "estado_publicacion": "generado"},
    )
    monkeypatch.setattr(
        panel,
        "_seleccion_fotos_desde_form",
        lambda cluster_id, form, noticias=None: (
            "https://img.test/cover.jpg",
            ["https://img.test/secondary-a.jpg", "https://img.test/secondary-b.jpg"],
        ),
    )
    monkeypatch.setattr(
        panel,
        "_guardar_seleccion_fotos",
        lambda cluster_id, foto_principal, fotos_secundarias: saved_photo_selections.append(
            (cluster_id, foto_principal, fotos_secundarias)
        ),
    )
    monkeypatch.setattr(
        panel.publicapress,
        "publicar_cluster",
        lambda cluster_id: {"ok": True, "url_wp": f"https://wp.test/{cluster_id}"},
    )
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda factory, cluster_id: removed.append((factory, cluster_id)),
    )

    response = panel.app.test_client().post(
        "/publicar/7",
        data={
            "return_to": "cluster_detalle",
            "save_photos_before_publish": "1",
            "foto_principal": "https://img.test/cover.jpg",
            "fotos_secundarias": [
                "https://img.test/secondary-a.jpg",
                "https://img.test/secondary-b.jpg",
            ],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert saved_photo_selections == [
        (
            7,
            "https://img.test/cover.jpg",
            ["https://img.test/secondary-a.jpg", "https://img.test/secondary-b.jpg"],
        )
    ]
    assert removed == [(panel.get_connection, 7)]


def test_bulk_generation_processes_saved_recommendations_sequentially_and_summarizes(monkeypatch):
    import app as panel

    saved = [
        {**candidate(cluster_id=1, title="Uno"), "reason": "Saved uno"},
        {**candidate(cluster_id=2, title="Dos"), "reason": "Saved dos"},
        {**candidate(cluster_id=3, title="Tres"), "reason": "Saved tres"},
        {**candidate(cluster_id=4, title="Cuatro"), "reason": "Saved cuatro"},
        {**candidate(cluster_id=5, title="Cinco"), "reason": "Saved cinco"},
    ]
    clusters = {
        1: {"id": 1, "estado_publicacion": "pendiente", "nota_ia": "persisted note"},
        2: {"id": 2, "estado_publicacion": "generado", "nota_ia": "skip me"},
        4: {"id": 4, "estado_publicacion": "pendiente", "nota_ia": ""},
        5: {"id": 5, "estado_publicacion": None, "nota_ia": "special note"},
    }
    generator_calls = []

    def load_saved(_factory):
        return list(saved)

    def generate(cluster_id, nota_ia=""):
        generator_calls.append((cluster_id, nota_ia))
        if cluster_id == 4:
            return {"ok": False, "mensaje": "boom"}
        return {"ok": True}

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=load_saved,
        EDITOR_JEFE_BULK_ARTICLE_GENERATOR=generate,
    )
    monkeypatch.setattr(panel, "obtener_cluster_db", lambda cluster_id: clusters.get(cluster_id))

    response = panel.app.test_client().post(
        "/editor-jefe-ia/generar-guardadas",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert generator_calls == [
        (1, "persisted note"),
        (4, ""),
        (5, "special note"),
    ]
    assert b"2 generados" in response.data
    assert b"2 omitidos" in response.data
    assert b"1 fallidos" in response.data
    assert b"Propuestas guardadas" in response.data


def test_real_context_to_provider_to_html_supports_empty_ai_selection(monkeypatch):
    import app as panel
    now = datetime(2026, 3, 7, 12, tzinfo=timezone.utc)
    row = {"cluster_id": 7, "titulo_representativo": "Mapped cluster",
           "cantidad_noticias": 2, "cantidad_fuentes": 2, "technical_score": 1.0,
           "tendencia": 0, "primera_noticia": now, "ultima_noticia": now,
           "ultima_publicacion": None, "newest_at": now}
    conn = type("Connection", (), {"close": lambda self: None})()
    factory_calls, seams, payloads = [], [], []
    factory = lambda: (factory_calls.append(True) or conn)
    loader = lambda value: lambda used: (seams.append(used) or value)
    monkeypatch.setattr(feature, "_load_eligible_clusters", lambda _conn: [row])
    monkeypatch.setattr(feature, "_load_recent_news", lambda _conn, _ids: [])
    for name, value in (("obtener_recientes_por_cluster", {7: {}}),
                        ("obtener_keywords_por_cluster", {7: []}), ("obtener_prioridades", [])):
        monkeypatch.setattr(feature, name, loader(value))
    monkeypatch.setattr(feature, "calcular_score_editorial", lambda *_: {"score_final": 51})
    monkeypatch.setattr(panel, "obtener_keywords_por_clusters_ids",
                        lambda used, _ids: (seams.append(used) or {7: ["mapped"]}))
    client = type("Client", (), {"select": lambda _, payload:
                  (payloads.append(json.loads(payload)) or {"selections": []})})
    configure_panel(panel, EDITOR_JEFE_CONTEXT_BUILDER=feature.build_editorial_context,
        EDITOR_JEFE_CONNECTION_FACTORY=factory, EDITOR_JEFE_CLIENT_FACTORY=client)
    response = panel.app.test_client().post(
        "/editor-jefe-ia",
        data={"maximum": "1", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert response.status_code == 200 and b"resultado v\xc3\xa1lido" in response.data
    assert factory_calls == [True] and seams == [conn] * 4
    assert payloads[0]["candidates"][0]["title"] == "Mapped cluster"


def test_build_cluster_keywords_for_panel_marks_priority_keywords_with_normalization():
    import app as panel

    result = panel.build_cluster_keywords_for_panel(
        {7: ["  Milei  ", "economía", "Otra"]},
        [
            {"keyword": "milei", "activo": True},
            {"keyword": " ECONOMÍA ", "activo": True},
            {"keyword": "otra", "activo": False},
        ],
    )

    assert result == {
        7: [
            {"label": "  Milei  ", "is_priority": True},
            {"label": "economía", "is_priority": True},
            {"label": "Otra", "is_priority": False},
        ]
    }


def test_index_highlights_existing_priority_keywords_in_cluster_list(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "listar_todos_los_clusters",
        lambda: [{
            "id": 7,
            "score": 42,
            "titulo_representativo": "Cluster destacado",
            "cantidad_noticias": 3,
            "cantidad_fuentes": 2,
            "ultima_noticia": None,
            "estado_publicacion": "pendiente",
            "url_wp": None,
        }],
    )
    monkeypatch.setattr(panel, "generar_candidatos", lambda _conn: [{"id": 7, "score_editorial": 55.0}])
    monkeypatch.setattr(panel, "obtener_keywords_por_clusters_ids", lambda _conn, _ids: {7: ["  Milei  ", "economía"]})
    monkeypatch.setattr(
        panel,
        "listar_keywords_prioridad_activas",
        lambda q=None: [{"keyword": "milei", "activo": True}],
    )

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    response = panel.app.test_client().get("/")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-priority-keyword="true"' in html
    assert re.search(r'data-priority-keyword="true"[\s\S]*?>\s*Milei\s*<', html)
    assert re.search(r'data-priority-keyword="false"[\s\S]*?>\s*economía\s*<', html)


def test_editor_jefe_ia_keywords_use_shared_keyword_modal_flow(monkeypatch):
    import app as panel

    selection = {
        "cluster_id": 7,
        "title": "Cluster destacado",
        "reason": "Relevant",
        "editorial_score": 55,
        "technical_score": 42,
        "news_count": 3,
        "source_count": 2,
    }

    monkeypatch.setattr(panel, "listar_keywords_prioridad_activas", lambda: [{"keyword": "milei", "activo": True}])
    monkeypatch.setattr(panel, "obtener_keywords_por_clusters_ids", lambda _conn, _ids: {7: ["Milei", "economía"]})

    class Connection:
        def close(self):
            return None

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    configure_panel(
        panel,
        EDITOR_JEFE_LOAD_SAVED_RECOMMENDATIONS=lambda *_: [dict(selection)],
    )

    response = panel.app.test_client().get("/editor-jefe-ia")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert html.count("openKeywordModal('") >= 2
    assert 'id="keywordModalForm"' in html
    assert 'action="/keywords-prioridad/upsert"' in html
    assert 'name="return_to" value="editor_jefe_ia"' in html
    assert "Milei" in html
    assert "economía" in html


def test_upsert_keyword_prioridad_redirects_back_to_editor_jefe_ia(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        rowcount = 1

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def rollback(self):
            executed.append(("rollback", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    response = panel.app.test_client().post(
        "/keywords-prioridad/upsert",
        data={
            "keyword": "Milei",
            "puntos": "10",
            "tipo": "keyword",
            "activo": "on",
            "return_to": "editor_jefe_ia",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/editor-jefe-ia")
    assert any("INSERT INTO keywords_prioridad" in sql for sql, _ in executed if isinstance(sql, str))
    assert ("commit", None) in executed


def test_failure_observability_uses_safe_categories_only(caplog):
    import app as panel
    failures = (
        lambda: feature.serialize_selection_payload([candidate(title="secret prompt" * 5000)], 1),
        lambda: feature.validate_selection_response({"secret output": "raw"}, [candidate()], 1),
        lambda: feature.OpenRouterSelectionClient(
            post=lambda *_a, **_k: (_ for _ in ()).throw(
                feature.requests.ConnectionError("sensitive provider exception")),
            api_key="secret-key", models=("one",), sleep=lambda _: None).select("secret prompt"),
    )
    with caplog.at_level("WARNING"):
        for failure in failures:
            with pytest.raises(feature.FeatureError):
                failure()
        panel.app.config["EDITOR_JEFE_CONTEXT_BUILDER"] = lambda *_: (_ for _ in ()).throw(
            RuntimeError("sensitive context exception"))
        panel.app.test_client().post(
            "/editor-jefe-ia",
            data={"maximum": "1", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
        )
    log_text = " ".join(record.getMessage() for record in caplog.records)
    assert all(name in log_text for name in ("payload_failure", "validation_failure",
        "provider_attempt_failed", "context_failure"))
    assert all(secret not in log_text for secret in ("secret prompt", "raw", "secret-key",
        "sensitive provider", "sensitive context"))


def test_descartar_cluster_can_return_to_editor_jefe_ia(monkeypatch):
    import app as panel

    executed = []
    removed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))
        def fetchone(self):
            return {"id": 7, "estado_publicacion": "pendiente"}
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()
        def commit(self):
            executed.append(("commit", None))
        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda factory, cluster_id: removed.append((factory, cluster_id)),
    )
    response = panel.app.test_client().post(
        "/descartar/7",
        data={"return_to": "editor_jefe_ia"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/editor-jefe-ia")
    assert any("UPDATE clusters_editoriales SET estado_publicacion = 'descartado'" in sql for sql, _ in executed if isinstance(sql, str))
    assert removed == [(panel.get_connection, 7)]
    assert ("commit", None) in executed


def test_split_cluster_blocks_generated_or_published_source_clusters(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            if len(executed) == 1:
                return {"id": 7, "estado_publicacion": "generado"}
            raise AssertionError("No further queries should run when split is blocked")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def rollback(self):
            executed.append(("rollback", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post(
        "/split-cluster/7",
        data={"noticias_split": ["11"]},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        ("SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s", (7,)),
        ("close", None),
    ]
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede partir un cluster generado. Revertí primero a pendiente si necesitás dividirlo.",
        )
    ]


def test_split_cluster_blocks_clusters_with_generation_in_flight(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            if len(executed) == 1:
                return {"id": 7, "estado_publicacion": "generando"}
            raise AssertionError("No further queries should run when split is blocked")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def rollback(self):
            executed.append(("rollback", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post(
        "/split-cluster/7",
        data={"noticias_split": ["11"]},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        ("SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s", (7,)),
        ("close", None),
    ]
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede partir un cluster mientras se está generando el artículo. Esperá a que termine el proceso.",
        )
    ]


def test_split_cluster_blocks_published_source_clusters_without_revert_guidance(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            if len(executed) == 1:
                return {"id": 7, "estado_publicacion": "publicado"}
            raise AssertionError("No further queries should run when split is blocked")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def rollback(self):
            executed.append(("rollback", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post(
        "/split-cluster/7",
        data={"noticias_split": ["11"]},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        ("SELECT id, estado_publicacion FROM clusters_editoriales WHERE id = %s", (7,)),
        ("close", None),
    ]
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede partir un cluster publicado porque ya tiene una nota activa en WordPress.",
        )
    ]


def test_revertir_estado_resets_generated_content_media_and_publication_url(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def __init__(self):
            self.fetchone_calls = 0

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            self.fetchone_calls += 1
            if self.fetchone_calls == 1:
                return {
                    "id": 7,
                    "estado_publicacion": "generado",
                    "requiere_revision_editorial": True,
                }
            raise AssertionError("Unexpected extra fetchone() call")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post("/revertir/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        (
            "SELECT id, estado_publicacion, requiere_revision_editorial FROM clusters_editoriales WHERE id = %s",
            (7,),
        ),
        (
            "UPDATE clusters_editoriales SET estado_publicacion = 'pendiente', contenido_ia = NULL, foto_principal = NULL, fotos_secundarias = '[]'::jsonb, url_wp = NULL, requiere_revision_editorial = FALSE, actualizado_en = NOW() WHERE id = %s",
            (7,),
        ),
        ("commit", None),
        ("close", None),
    ]
    assert pop_flashes(client) == [("info", "Revertido a pendiente")]


def test_revertir_estado_blocks_published_clusters(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def __init__(self):
            self.fetchone_calls = 0

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            self.fetchone_calls += 1
            if self.fetchone_calls == 1:
                return {"id": 7, "estado_publicacion": "publicado"}
            raise AssertionError("Unexpected extra fetchone() call")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post("/revertir/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        (
            "SELECT id, estado_publicacion, requiere_revision_editorial FROM clusters_editoriales WHERE id = %s",
            (7,),
        ),
        ("close", None),
    ]
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede revertir un cluster publicado porque la nota sigue activa en WordPress.",
        )
    ]


def test_revertir_estado_blocks_clusters_with_generation_in_flight(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def __init__(self):
            self.fetchone_calls = 0

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            self.fetchone_calls += 1
            if self.fetchone_calls == 1:
                return {"id": 7, "estado_publicacion": "generando"}
            raise AssertionError("Unexpected extra fetchone() call")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post("/revertir/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        (
            "SELECT id, estado_publicacion, requiere_revision_editorial FROM clusters_editoriales WHERE id = %s",
            (7,),
        ),
        ("close", None),
    ]
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede revertir un cluster mientras la generación sigue en curso.",
        )
    ]


def test_revertir_estado_from_descartado_preserves_generated_assets(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def __init__(self):
            self.fetchone_calls = 0

        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))

        def fetchone(self):
            self.fetchone_calls += 1
            if self.fetchone_calls == 1:
                return {"id": 7, "estado_publicacion": "descartado"}
            raise AssertionError("Unexpected extra fetchone() call")

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            executed.append(("commit", None))

        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())

    client = panel.app.test_client()
    response = client.post("/revertir/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert executed == [
        (
            "SELECT id, estado_publicacion, requiere_revision_editorial FROM clusters_editoriales WHERE id = %s",
            (7,),
        ),
        (
            "UPDATE clusters_editoriales SET estado_publicacion = 'pendiente', actualizado_en = NOW() WHERE id = %s",
            (7,),
        ),
        ("commit", None),
        ("close", None),
    ]
    assert pop_flashes(client) == [("info", "Revertido a pendiente")]


def test_publicar_cluster_removes_saved_recommendation_on_success(monkeypatch):
    import app as panel

    removed = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {"id": cluster_id, "estado_publicacion": "generado"},
    )
    monkeypatch.setattr(
        panel.publicapress,
        "publicar_cluster",
        lambda cluster_id: {"ok": True, "url_wp": f"https://wp.test/{cluster_id}"},
    )
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda factory, cluster_id: removed.append((factory, cluster_id)),
    )

    client = panel.app.test_client()
    response = client.post("/publicar/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert removed == [(panel.get_connection, 7)]


def test_publicar_cluster_blocks_when_editorial_review_is_required(monkeypatch):
    import app as panel

    publish_calls = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "generado",
            "requiere_revision_editorial": True,
        },
    )
    monkeypatch.setattr(
        panel.publicapress,
        "publicar_cluster",
        lambda cluster_id: publish_calls.append(cluster_id) or {"ok": True, "url_wp": "https://wp.test/7"},
    )

    client = panel.app.test_client()
    response = client.post("/publicar/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert publish_calls == []
    assert pop_flashes(client) == [
        (
            "warning",
            "No se puede publicar hasta aprobar la revisión editorial en el detalle del cluster.",
        )
    ]


def test_aprobar_revision_editorial_clears_flag_and_redirects_to_cluster(monkeypatch):
    import app as panel

    updates = []

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "generado",
            "requiere_revision_editorial": True,
        },
    )
    monkeypatch.setattr(
        panel.publicador,
        "set_requiere_revision_editorial",
        lambda cluster_id, requires_review: updates.append((cluster_id, requires_review)),
    )

    client = panel.app.test_client()
    response = client.post("/aprobar-revision-editorial/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")
    assert updates == [(7, False)]
    assert pop_flashes(client) == [("success", "Revisión editorial aprobada. Ya podés publicar.")]


def test_publish_succeeds_after_editorial_review_approval(monkeypatch):
    import app as panel

    state = {
        "id": 7,
        "estado_publicacion": "generado",
        "requiere_revision_editorial": True,
    }
    published = []

    monkeypatch.setattr(panel, "obtener_cluster_db", lambda cluster_id: dict(state))
    monkeypatch.setattr(
        panel.publicador,
        "set_requiere_revision_editorial",
        lambda cluster_id, requires_review: state.update(requiere_revision_editorial=requires_review),
    )
    monkeypatch.setattr(
        panel.publicapress,
        "publicar_cluster",
        lambda cluster_id: published.append(cluster_id) or {"ok": True, "url_wp": f"https://wp.test/{cluster_id}"},
    )
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda *_args: None,
    )

    client = panel.app.test_client()
    approval_response = client.post("/aprobar-revision-editorial/7", follow_redirects=False)
    publish_response = client.post("/publicar/7", follow_redirects=False)

    assert approval_response.status_code == 302
    assert publish_response.status_code == 302
    assert publish_response.headers["Location"].endswith("/cluster/7")
    assert published == [7]
    assert state["requiere_revision_editorial"] is False


def test_publicar_cluster_preserves_success_when_cleanup_fails(monkeypatch):
    import app as panel

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {"id": cluster_id, "estado_publicacion": "generado"},
    )
    monkeypatch.setattr(
        panel.publicapress,
        "publicar_cluster",
        lambda cluster_id: {"ok": True, "url_wp": f"https://wp.test/{cluster_id}"},
    )
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    response = panel.app.test_client().post("/publicar/7", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cluster/7")



def test_descartar_cluster_preserves_success_when_cleanup_fails(monkeypatch):
    import app as panel

    executed = []

    class Cursor:
        def execute(self, sql, params=None):
            executed.append((" ".join(sql.split()), params))
        def fetchone(self):
            return {"id": 7, "estado_publicacion": "pendiente"}
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False

    class Connection:
        def cursor(self):
            return Cursor()
        def commit(self):
            executed.append(("commit", None))
        def close(self):
            executed.append(("close", None))

    monkeypatch.setattr(panel, "get_connection", lambda: Connection())
    monkeypatch.setitem(
        panel.app.config,
        "EDITOR_JEFE_DELETE_SAVED_RECOMMENDATION",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    response = panel.app.test_client().post(
        "/descartar/7",
        data={"return_to": "editor_jefe_ia"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/editor-jefe-ia")
    assert ("commit", None) in executed


def test_post_zero_and_failures_show_no_partial_recommendation():
    import app as panel
    client = panel.app.test_client()
    configure_panel(panel, EDITOR_JEFE_CONTEXT_BUILDER=lambda *_: [],
                    EDITOR_JEFE_CONNECTION_FACTORY=object())
    zero = client.post(
        "/editor-jefe-ia",
        data={"maximum": "2", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert zero.status_code == 200 and b"No se encontraron clusters elegibles" in zero.data
    invalid = client.post(
        "/editor-jefe-ia",
        data={"maximum": "0", "minimum_editorial_score": DEFAULT_MINIMUM_EDITORIAL_SCORE},
    )
    assert invalid.status_code == 200 and b"n\xc3\xbamero entero positivo" in invalid.data
    assert b"Recomendaci" not in invalid.data
