from bs4 import BeautifulSoup, Comment
import bleach
from markupsafe import Markup


ALLOWED_TAGS = (
    'p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li',
    'blockquote', 'h2', 'h3', 'h4', 'a', 'img'
)
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'title'],
}
ALLOWED_PROTOCOLS = ('http', 'https', 'mailto')
DANGEROUS_TAGS = ('script', 'style', 'iframe', 'object', 'embed')


def sanitize_article_html(raw_html):
    if not raw_html:
        return ''

    soup = BeautifulSoup(raw_html, 'html.parser')

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(DANGEROUS_TAGS):
        tag.decompose()

    cleaned = bleach.clean(
        str(soup),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )

    cleaned_soup = BeautifulSoup(cleaned, 'html.parser')
    for image in cleaned_soup.find_all('img'):
        if not (image.get('src') or '').strip():
            image.decompose()

    return ''.join(str(node) for node in cleaned_soup.contents)


def sanitize_article_markup(raw_html):
    return Markup(sanitize_article_html(raw_html))
