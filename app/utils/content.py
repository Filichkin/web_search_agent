import re
import trafilatura

from app.utils.constants import TRANFILATURA_MAX_CHARS
from app.utils.logging import logger


_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _clean_text(s: str) -> str:
    s = s or ''
    s = _HTML_TAG_RE.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def fetch_desc_trafilatura(
        url: str,
        fallback_text: str = '',
        max_chars: int = TRANFILATURA_MAX_CHARS
) -> str:
    """
    Пытается извлечь краткое описание страницы через Trafilatura.
    Если не удалось (пусто), возвращает fallback_text (очищенный).
    """
    extracted = ''

    try:
        logger.info(f'[Trafilatura] fetch url: {url}')
        html = trafilatura.fetch_url(url)
        if html:
            txt = trafilatura.extract(
                html,
                url=url,
                output_format='txt',
                include_comments=False,
                include_tables=False,
                favor_recall=True,
            )
            extracted = _clean_text(txt)[:max_chars] if txt else ''
    except Exception as e:
        logger.warning(f'[Trafilatura] исключение при извлечении: {e}')

    if extracted:
        snippet = extracted[:200]
        logger.info(
            f'[Trafilatura] OK ({len(extracted)} симв.): "{snippet}..."'
            )
        return extracted

    # fallback
    fallback_text = _clean_text(fallback_text)[:max_chars]
    if fallback_text:
        logger.info(
            f'[Trafilatura] fallback использован ({len(fallback_text)} симв.)'
            )
    else:
        logger.warning('[Trafilatura] fallback пуст')
    return fallback_text
