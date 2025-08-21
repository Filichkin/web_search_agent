import json
from typing import Any, Callable, Optional, Dict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.tools import StructuredTool

from pipeline.utils.content import fetch_desc_trafilatura
from pipeline.utils.logging import logger
from pipeline.utils.storage import save_search_results


class SearchLoggingCallback(BaseCallbackHandler):
    """
    Логирует входные данные инструментов поиска (например, brave-search).
    """
    def on_tool_start(self, serialized, input_str, **kwargs):
        # serialized содержит метаданные инструмента (name/description и пр.)
        tool_name = (serialized or {}).get('name', '').lower()

        # input_str в LC 0.2 бывает и dict, и str — поддержим оба варианта
        query_text = None
        if isinstance(input_str, dict):
            # У server-brave-search поле обычно называется 'query'
            query_text = input_str.get('query')
            if query_text is None:
                # иногда модель может слать просто "input"
                query_text = input_str.get('input')
        else:
            query_text = str(input_str)

        # Логируем всё, что связано с поиском
        if any(option in tool_name for option in ['search', 'brave', 'web']):
            logger.info(
                '🔎 [ПОИСК] Инструмент: %s | Запрос: %r', tool_name, query_text
                )


def wrap_search_tool(
        orig_tool,
        get_raw_user_input: Callable[[], Optional[str]],
        *,
        max_calls_per_message: int = 2
):
    """
    Обёртка поискового инструмента:
    - подменяет kwargs['query'] на сырое сообщение пользователя,
    - предотвращает зацикливание,
    - обогащает результаты Trafilatura и возвращает Markdown-контекст,
    - логирует и сохраняет JSON.
    """

    called_queries: set[str] = set()
    call_count: int = 0
    last_seen_raw: Optional[str] = None

    class _Args(BaseModel):
        query: str = Field(description='Search query string')

        class Config:
            extra = 'allow'

    async def _acall(**kwargs: Dict[str, Any]) -> Any:
        nonlocal call_count, called_queries, last_seen_raw

        raw = get_raw_user_input()

        # сброс контекста при новом пользовательском сообщении
        if raw != last_seen_raw:
            called_queries = set()
            call_count = 0
            last_seen_raw = raw

        # лог до правки
        try:
            logger.info(
                '🔎 [ПОИСК] До правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        # всегда подставляем полный исходный текст пользователя
        if raw:
            kwargs = {**kwargs, 'query': raw}

        # анти-петля
        qnorm = (kwargs.get('query') or '').strip().lower()
        if qnorm in called_queries:
            return (
                'Поиск уже выполнен по этому же запросу; '
                'используй найденные источники ниже.'
                )
        if call_count >= max_calls_per_message:
            return (
                'Достигнут лимит поисковых запросов для этого сообщения; '
                'сформируй ответ по уже найденным источникам.'
                )
        called_queries.add(qnorm)
        call_count += 1

        # лог после правки
        try:
            logger.info(
                '🔎 [ПОИСК] После правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        # вызываем оригинальный MCP-инструмент
        result = await orig_tool.ainvoke(kwargs)

        # сохраняем (как есть, без модификаций)
        try:
            saved = save_search_results(kwargs.get('query', ''), result)
            logger.info('💾 Сохранено результатов: %s', saved)
        except Exception as e:
            logger.warning('Не удалось сохранить результаты поиска: %s', e)

        # --- ОБОГАЩЕНИЕ ДЛЯ КОНТЕКСТА МОДЕЛИ ---
        enriched = []
        if isinstance(result, list):
            for item, element in enumerate(result, start=1):
                if len(enriched) >= 5:
                    break
                try:
                    data = (
                        json.loads(element)
                        if isinstance(element, str) else element
                        )
                except Exception as error:
                    logger.warning(
                        '[%s] Не удалось распарсить элемент: %s',
                        item,
                        error
                        )
                    continue

                url = (data.get('url') or '').strip()
                title = (data.get('title') or '').strip()
                desc = (data.get('description') or '').strip()

                logger.info('[%s] Trafilatura для %s', item, url or '<no-url>')
                # всегда пытаемся вытащить текст;
                # если пусто — берём исходный desc
                summary = fetch_desc_trafilatura(
                    url,
                    fallback_text=desc,
                    max_chars=2000
                    )
                # ужмём до пары коротких предложений
                # (визуально 220–300 символов)
                snippet = summary.replace('\n', ' ').strip()
                if len(snippet) > 2000:
                    snippet = snippet[:1500] + '...'

                enriched.append({
                    'url': url,
                    'title': title or url,
                    'snippet': snippet
                })
                # logger.info(f'ENRICHED: {enriched}')

        # собираем удобоваримый Markdown, который увидит модель
        if enriched:
            lines = [
                '### Источники (обогащены Trafilatura — используй при ответе):'
                ]
            for source in enriched:
                lines.append(f'- [{source["title"]}]({source["url"]})')
                lines.append(f'  {source["snippet"]}')
                lines.append('')
            context_md = '\n'.join(lines)
        else:
            # если обогащение не удалось — вернём как есть
            context_md = (
                'Не удалось обогатить результаты; '
                'используй исходные ссылки из поиска.'
                )
        # logger.info('🔗 [ПОИСК] Контекст для модели:\n%s', context_md)
        return context_md

    return StructuredTool.from_function(
        coroutine=_acall,
        name=orig_tool.name,
        description=getattr(orig_tool, 'description', ''),
        args_schema=_Args,
        return_direct=False,  # пусть модель видит контекст и сама пишет ответ
    )
