"""Read-only context assembly and selection for Editor Jefe IA."""

import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

from trh.infrastructure.prompt_loader import load_prompt_text

from pipeline.seleccionar_publicables import (
    calcular_score_editorial,
    obtener_keywords_por_cluster,
    obtener_prioridades,
    obtener_recientes_por_cluster,
)


_ELIGIBLE_CLUSTERS_SQL = """
SELECT
    ce.id AS cluster_id,
    ce.titulo_representativo,
    ce.cantidad_noticias,
    ce.cantidad_fuentes,
    ce.score AS technical_score,
    ce.tendencia,
    ce.primera_noticia,
    ce.ultima_noticia,
    ce.ultima_publicacion,
    MAX(COALESCE(n.fecha_publicacion, n.fecha_extraccion)) AS newest_at
FROM clusters_editoriales ce
JOIN noticias_historico n ON n.cluster_id = ce.id
WHERE COALESCE(ce.estado_publicacion, 'pendiente') = 'pendiente'
  AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
      >= NOW() - INTERVAL '3 days'
GROUP BY ce.id, ce.titulo_representativo, ce.cantidad_noticias,
         ce.cantidad_fuentes, ce.score, ce.tendencia,
         ce.primera_noticia, ce.ultima_noticia, ce.ultima_publicacion
ORDER BY newest_at DESC, ce.id DESC
"""

_RECENT_NEWS_SQL = """
WITH qualifying AS (
    SELECT
        n.id,
        n.cluster_id,
        n.titulo,
        n.fuente,
        n.texto_completo,
        COALESCE(n.fecha_publicacion, n.fecha_extraccion) AS effective_at
    FROM noticias_historico n
    WHERE n.cluster_id = ANY(%s)
      AND COALESCE(n.fecha_publicacion, n.fecha_extraccion)
          >= NOW() - INTERVAL '3 days'
), ranked AS (
    SELECT n.*, ROW_NUMBER() OVER (
        PARTITION BY n.cluster_id
        ORDER BY n.effective_at DESC, n.id DESC
    ) AS rn
    FROM qualifying n
)
SELECT id, cluster_id, titulo, fuente, texto_completo, effective_at
FROM ranked
WHERE rn <= 3
ORDER BY cluster_id, effective_at DESC, id DESC
"""


def _normalized_text(value, limit, fallback=""):
    normalized = " ".join(str(value).split()) if value is not None else ""
    return (normalized or fallback)[:limit]


def _normalized_keywords(values):
    bounded = {
        normalized[:120]
        for value in values
        if (normalized := _normalized_text(value, 120))
    }
    return sorted(bounded)[:8]


def _serialize_timestamp(value, label):
    if value is None:
        raise ValueError(f"Missing {label} timestamp")
    return value.isoformat()


def _load_eligible_clusters(conn):
    with conn.cursor() as cursor:
        cursor.execute(_ELIGIBLE_CLUSTERS_SQL)
        return cursor.fetchall()


def _load_recent_news(conn, cluster_ids):
    with conn.cursor() as cursor:
        cursor.execute(_RECENT_NEWS_SQL, (cluster_ids,))
        return cursor.fetchall()


def build_editorial_context(connection_factory, panel_keywords_loader):
    """Return deterministic, bounded candidate mappings using read-only queries."""
    conn = connection_factory()
    try:
        clusters = _load_eligible_clusters(conn)
        if not clusters:
            return []
        clusters.sort(
            key=lambda row: (row["newest_at"], row["cluster_id"]), reverse=True
        )

        recent_counts = obtener_recientes_por_cluster(conn)
        score_keywords = obtener_keywords_por_cluster(conn)
        priorities = obtener_prioridades(conn)
        cluster_ids = [row["cluster_id"] for row in clusters]
        panel_keywords = panel_keywords_loader(conn, cluster_ids)
        news_rows = _load_recent_news(conn, cluster_ids)

        news_by_cluster = {}
        for row in news_rows:
            items = news_by_cluster.setdefault(row["cluster_id"], [])
            if len(items) >= 3:
                continue
            items.append({
                "title": _normalized_text(row.get("titulo"), 300),
                "source": _normalized_text(row.get("fuente"), 100),
                "effective_at": _serialize_timestamp(
                    row.get("effective_at"), "news effective"
                ),
                "excerpt": _normalized_text(row.get("texto_completo"), 600),
            })

        candidates = []
        for row in clusters:
            cluster_id = row["cluster_id"]
            score_cluster = {"id": cluster_id, **row}
            score = calcular_score_editorial(
                score_cluster,
                recent_counts.get(cluster_id, {
                    "noticias_2h": 0,
                    "noticias_6h": 0,
                    "noticias_24h": 0,
                }),
                score_keywords.get(cluster_id, []),
                priorities,
            )
            candidates.append({
                "cluster_id": cluster_id,
                "title": _normalized_text(
                    row.get("titulo_representativo"), 300, "(Sin título)"
                ),
                "technical_score": (
                    0.0 if row.get("technical_score") is None
                    else row["technical_score"]
                ),
                "editorial_score": score["score_final"],
                "news_count": row["cantidad_noticias"],
                "source_count": row["cantidad_fuentes"],
                "newest_at": _serialize_timestamp(row.get("newest_at"), "cluster newest"),
                "keywords": _normalized_keywords(panel_keywords.get(cluster_id, [])),
                "recent_news": news_by_cluster.get(cluster_id, []),
            })

        return candidates
    finally:
        conn.close()

EDITOR_JEFE_SYSTEM_PROMPT = load_prompt_text(
    "EDITOR_JEFE_SYSTEM_PROMPT_FILE",
    logger,
)
SELECTION_BATCH_LIMIT = 5
PAYLOAD_BYTE_LIMIT = 48_000
RESPONSE_TOKEN_LIMIT = 1_200

_LOAD_RECOMMENDATIONS_SQL = """
SELECT
    r.cluster_id,
    r.title,
    r.reason,
    r.editorial_score,
    r.technical_score,
    r.news_count,
    r.source_count,
    r.newest_at,
    r.recommended_at,
    COALESCE(ce.estado_publicacion, 'pendiente') AS estado_publicacion,
    COALESCE(ce.requiere_revision_editorial, FALSE) AS requiere_revision_editorial
FROM editor_jefe_ia_recommendations r
LEFT JOIN clusters_editoriales ce ON ce.id = r.cluster_id
ORDER BY r.recommended_at DESC, r.cluster_id DESC
"""

_SAVE_RECOMMENDATION_SQL = """
INSERT INTO editor_jefe_ia_recommendations (
    cluster_id,
    title,
    reason,
    editorial_score,
    technical_score,
    news_count,
    source_count,
    newest_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz)
ON CONFLICT (cluster_id) DO NOTHING
"""

_DELETE_RECOMMENDATION_SQL = """
DELETE FROM editor_jefe_ia_recommendations
WHERE cluster_id = %s
"""


class FeatureError(Exception):
    """Safe feature failure boundary with a non-sensitive category."""

    def __init__(self, message, code="feature_failure"):
        super().__init__(message)
        self.code = code


def _failure(code, message):
    logger.warning("editor_jefe.%s", code)
    return FeatureError(message, code)


def record_context_failure():
    logger.warning("editor_jefe.context_failure")


def _parse_positive_integer(raw, message, code):
    if not isinstance(raw, str) or not re.fullmatch(r"[1-9]\d*", raw):
        raise FeatureError(message, code)
    return int(raw)


def parse_maximum(raw):
    return _parse_positive_integer(
        raw, "A positive whole number is required", "input_failure"
    )


def parse_minimum_editorial_score(raw):
    return _parse_positive_integer(
        raw,
        "A positive whole number is required for editorial score",
        "minimum_score_failure",
    )


def serialize_selection_payload(candidates, batch_size):
    payload = json.dumps(
        {"batch_size": batch_size, "candidates": candidates}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > PAYLOAD_BYTE_LIMIT:
        raise _failure("payload_failure", "Selection request is too large")
    return payload


def validate_selection_response(body, candidates, maximum):
    def invalid(reason):
        logger.warning("editor_jefe.validation_failure reason=%s", reason)
        return FeatureError("Invalid selection response", "validation_failure")

    if not isinstance(body, dict) or set(body) != {"selections"}:
        raise invalid("top_level_schema")
    selections = body["selections"]
    if not isinstance(selections, list) or len(selections) > min(maximum, len(candidates)):
        raise invalid("selection_count")
    eligible = {item["cluster_id"]: item for item in candidates}
    reasons = {}
    for selection in selections:
        if not isinstance(selection, dict) or set(selection) != {"cluster_id", "reason"}:
            raise invalid("selection_schema")
        cluster_id, reason = selection["cluster_id"], selection["reason"]
        if (isinstance(cluster_id, bool) or not isinstance(cluster_id, int)
                or cluster_id not in eligible or cluster_id in reasons):
            raise invalid("cluster_id")
        if not isinstance(reason, str):
            raise invalid("reason_type")
        reason = reason.strip()
        if not reason:
            raise invalid("reason_empty")
        if len(reason) > 240:
            raise invalid("reason_too_long")
        if any(unicodedata.category(char) == "Cc" for char in reason):
            raise invalid("reason_control_character")
        reasons[cluster_id] = reason
    return [{**item, "reason": reasons[item["cluster_id"]]}
            for item in candidates if item["cluster_id"] in reasons]


class OpenRouterSelectionClient:
    def __init__(self, post=requests.post, api_key=None, models=None, sleep=time.sleep):
        self.post = post
        self.sleep = sleep
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self.models = models or (
            os.getenv("OPENROUTER_MODEL_PRIMARY", "openrouter/free"),
            os.getenv("OPENROUTER_MODEL_FALLBACK", "deepseek/deepseek-v4-flash"),
        )
        self.url = os.getenv(
            "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"
        )

    def select(self, payload):
        if not self.api_key:
            logger.warning(
                "editor_jefe.provider_unavailable model=%s "
                "error_category=configuration http_status=none",
                self.models[0] if self.models else "none",
            )
            raise FeatureError(
                "Selection provider unavailable", "provider_configuration_failure"
            )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://trh.local",
            "X-Title": "TRH Editor Jefe IA",
        }
        for model in self.models:
            response = None
            try:
                response = self.post(
                    self.url, headers=headers,
                    json={"model": model, "messages": [
                        {"role": "system", "content": EDITOR_JEFE_SYSTEM_PROMPT},
                        {"role": "user", "content": payload},
                    ], "temperature": 0, "max_tokens": RESPONSE_TOKEN_LIMIT,
                          "response_format": {"type": "json_object"}}, timeout=70,
                )
                if response.status_code == 429:
                    logger.warning(
                        "editor_jefe.provider_attempt_failed model=%s "
                        "error_category=rate_limit http_status=429", model,
                    )
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return json.loads(content.strip())
            except requests.RequestException as error:
                error_response = getattr(error, "response", None)
                status_source = response if response is not None else error_response
                http_status = getattr(status_source, "status_code", None)
                logger.warning(
                    "editor_jefe.provider_attempt_failed model=%s "
                    "error_category=http_error http_status=%s", model, http_status,
                )
            except ValueError:
                logger.warning(
                    "editor_jefe.provider_attempt_failed model=%s "
                    "error_category=malformed_response http_status=%s",
                    model, getattr(response, "status_code", None),
                )
            except (IndexError, KeyError, TypeError):
                logger.warning(
                    "editor_jefe.provider_attempt_failed model=%s "
                    "error_category=response_schema http_status=%s",
                    model, getattr(response, "status_code", None),
                )
        raise FeatureError("Selection provider unavailable", "provider_failure")


def load_saved_recommendations(connection_factory):
    conn = connection_factory()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_LOAD_RECOMMENDATIONS_SQL)
            return cursor.fetchall()
    finally:
        conn.close()


def save_recommendations(connection_factory, selections):
    if not selections:
        return
    conn = connection_factory()
    try:
        with conn.cursor() as cursor:
            for item in selections:
                cursor.execute(
                    _SAVE_RECOMMENDATION_SQL,
                    (
                        item["cluster_id"],
                        item["title"],
                        item["reason"],
                        item["editorial_score"],
                        item["technical_score"],
                        item["news_count"],
                        item["source_count"],
                        item["newest_at"],
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def delete_saved_recommendation(connection_factory, cluster_id):
    conn = connection_factory()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_DELETE_RECOMMENDATION_SQL, (cluster_id,))
        conn.commit()
    finally:
        conn.close()


@dataclass(frozen=True)
class SelectionOutcome:
    selections: list
    total_batches: int
    failed_batches: int
    failure_codes: tuple = ()


def select_recommendations(candidates, batch_size, client):
    selections = []
    failure_codes = []
    limited_candidates = candidates[:batch_size]
    batches = [
        limited_candidates[index:index + SELECTION_BATCH_LIMIT]
        for index in range(0, len(limited_candidates), SELECTION_BATCH_LIMIT)
    ]
    total_batches = len(batches)
    for batch_index, batch in enumerate(batches, start=1):
        batch_maximum = len(batch)
        logger.info(
            "editor_jefe.batch_started batch_index=%s batch_count=%s batch_size=%s",
            batch_index, total_batches, batch_maximum,
        )
        try:
            payload = serialize_selection_payload(batch, batch_maximum)
            batch_selections = validate_selection_response(
                client.select(payload), batch, batch_maximum
            )
            selections.extend(batch_selections)
            logger.info(
                "editor_jefe.batch_completed batch_index=%s batch_count=%s "
                "batch_size=%s selection_count=%s",
                batch_index, total_batches, batch_maximum, len(batch_selections),
            )
        except FeatureError as error:
            failure_codes.append(error.code)
            logger.warning(
                "editor_jefe.batch_failed batch_index=%s batch_count=%s batch_size=%s "
                "error_category=%s",
                batch_index, total_batches, batch_maximum, error.code,
            )
            if error.code == "provider_configuration_failure":
                failure_codes.extend(
                    [error.code] * (total_batches - batch_index)
                )
                break
    return SelectionOutcome(
        selections=selections,
        total_batches=total_batches,
        failed_batches=len(failure_codes),
        failure_codes=tuple(failure_codes),
    )
