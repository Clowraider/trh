import app as panel

from trh.infrastructure.html_sanitizer import sanitize_article_html


def test_sanitize_article_html_removes_scripts_events_and_javascript_urls():
    raw_html = (
        '<p onclick="alert(1)">Hola<script>alert(1)</script></p>'
        '<a href="javascript:alert(2)">Link</a>'
        '<img src="javascript:alert(3)" onerror="alert(4)" alt="boom">'
    )

    cleaned = sanitize_article_html(raw_html)

    assert "<script" not in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned
    assert "javascript:" not in cleaned
    assert "alert(1)" not in cleaned
    assert "<a>Link</a>" in cleaned
    assert "<img" not in cleaned


def test_sanitize_article_html_preserves_editorial_formatting_safe_links_and_images():
    raw_html = (
        "<h2>Subtítulo</h2>"
        "<p><strong>Texto</strong> con <em>énfasis</em> y "
        '<a href="https://example.com/nota" title="Fuente">fuente</a>.</p>'
        '<blockquote>Contexto</blockquote>'
        '<ul><li>Uno</li><li>Dos</li></ul>'
        '<img src="https://example.com/foto.jpg" alt="Foto" title="Portada">'
    )

    cleaned = sanitize_article_html(raw_html)

    assert "<h2>Subtítulo</h2>" in cleaned
    assert "<strong>Texto</strong>" in cleaned
    assert "<em>énfasis</em>" in cleaned
    assert '<a href="https://example.com/nota" title="Fuente">fuente</a>' in cleaned
    assert "<blockquote>Contexto</blockquote>" in cleaned
    assert "<ul><li>Uno</li><li>Dos</li></ul>" in cleaned
    assert '<img' in cleaned
    assert 'src="https://example.com/foto.jpg"' in cleaned
    assert 'alt="Foto"' in cleaned
    assert 'title="Portada"' in cleaned


def test_cluster_detail_renders_sanitized_article_preview_without_destroying_formatting(monkeypatch):
    payload = {
        "titulo": "Artículo generado",
        "categoria": "Sociedad",
        "resumen": "Resumen breve",
        "articulo": (
            '<h2 onclick="evil()">Bajada</h2>'
            '<p>Intro<script>alert(9)</script></p>'
            '<p><img src="https://img.test/foto.jpg" alt="OK" style="width:100%"></p>'
        ),
    }

    monkeypatch.setattr(
        panel,
        "obtener_cluster_db",
        lambda cluster_id: {
            "id": cluster_id,
            "estado_publicacion": "generado",
            "score": 77,
            "contenido_ia": payload,
        },
    )
    monkeypatch.setattr(panel, "obtener_noticias_cluster", lambda cluster_id: [])

    response = panel.app.test_client().get("/cluster/7")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<div class="contenido-preview">' in html
    assert '<h2>Bajada</h2>' in html
    assert '<p>Intro</p>' in html
    assert '<img' in html
    assert 'src="https://img.test/foto.jpg"' in html
    assert 'alt="OK"' in html
    assert "alert(9)" not in html
    assert "onclick" not in html
    assert 'style="width:100%"' not in html
