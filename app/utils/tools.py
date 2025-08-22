import json
from typing import Any, Callable, Optional, Dict

from langchain_core.callbacks import BaseCallbackHandler
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from app.utils.constants import (
    SNIPPET_MAX_CHARS,
    TRANFILATURA_MAX_CHARS,
)
from app.utils.content import fetch_desc_trafilatura
from app.utils.logging import logger
from app.utils.storage import save_search_results


class SearchLoggingCallback(BaseCallbackHandler):
    '''
    Логирует входные данные инструментов поиска (например, brave-search).
    '''

    def on_tool_start(self, serialized, input_str, **kwargs):
        # serialized содержит метаданные инструмента (name/description и пр.)
        tool_name = (serialized or {}).get('name', '').lower()

        # input_str в LC 0.2 бывает и dict, и str — поддержим оба варианта
        if isinstance(input_str, dict):
            # у server-brave-search поле обычно называется 'query'
            query_text = input_str.get('query')
            if query_text is None:
                # иногда модель может слать просто 'input'
                query_text = input_str.get('input')
        else:
            query_text = str(input_str)

        # логируем всё, что связано с поиском
        if any(opt in tool_name for opt in ['search', 'brave', 'web']):
            logger.info(
                '🔎 [ПОИСК] Инструмент: {} | Запрос: {!r}',
                tool_name,
                query_text,
            )


def wrap_search_tool(
    orig_tool,
    get_raw_user_input: Callable[[], Optional[str]],
    *,
    max_calls_per_message: int = 1,
):
    '''
    Обёртка поискового инструмента:
    - подменяет kwargs['query'] на сырое сообщение пользователя,
    - предотвращает зацикливание,
    - обогащает результаты Trafilatura и возвращает Markdown-контекст,
    - логирует и сохраняет JSON.
    '''

    called_queries: set[str] = set()
    call_count: int = 0
    last_seen_raw: Optional[str] = None

    class _Args(BaseModel):
        query: str = Field(description='Search query string')

        # pydantic v2
        model_config = {'extra': 'allow'}

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
                '🔎 [ПОИСК] До правки | tool={} | input={!r}',
                orig_tool.name,
                kwargs,
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
                '🔎 [ПОИСК] После правки | tool={} | input={!r}',
                orig_tool.name,
                kwargs,
            )
        except Exception:
            pass

        # вызываем оригинальный MCP-инструмент
        result = await orig_tool.ainvoke(kwargs)

        # --- ОБОГАЩЕНИЕ ДЛЯ КОНТЕКСТА МОДЕЛИ ---
        enriched = []
        if isinstance(result, list):
            for item, element in enumerate(result, start=1):
                if len(enriched) >= 5:
                    break
                try:
                    data = (
                        json.loads(element)
                        if isinstance(element, str)
                        else element
                    )
                except Exception as error:
                    logger.warning(
                        '[{}] Не удалось распарсить элемент: {}',
                        item,
                        error,
                    )
                    continue

                url = (data.get('url') or '').strip()
                title = (data.get('title') or '').strip()
                desc = (data.get('description') or '').strip()

                logger.info('[{}] Trafilatura для {}', item, url or '<no-url>')

                # всегда пытаемся вытащить текст;
                # если пусто — берём исходный desc
                summary = fetch_desc_trafilatura(
                    url,
                    fallback_text=desc,
                    max_chars=TRANFILATURA_MAX_CHARS,
                )

                snippet = summary.replace('\n', ' ').strip()
                low = snippet.lower()
                if (
                    'подтвердите, что запросы отправляли вы' in low
                    or 'captcha' in low
                ):
                    snippet = (desc or '').replace('\n', ' ').strip()
                snippet = snippet[:SNIPPET_MAX_CHARS] + '...'

                enriched.append(
                    {
                        'url': url,
                        'title': title or url,
                        'snippet': snippet,
                    }
                )

        # сохраняем ТОЛЬКО enriched в JSON
        try:
            saved = save_search_results(
                kwargs.get('query', ''),
                enriched,
                already_enriched=True,
            )
            logger.info('💾 Сохранено enriched-результатов: {}', saved)
        except Exception as e:
            logger.warning(
                'Не удалось сохранить enriched-результаты: {}',
                e,
            )

        # собираем markdown-контекст для модели
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
            context_md = (
                'Не удалось обогатить результаты; '
                'используй исходные ссылки из поиска.'
            )

        return context_md

    return StructuredTool.from_function(
        coroutine=_acall,
        name=orig_tool.name,
        description=getattr(orig_tool, 'description', ''),
        args_schema=_Args,
        return_direct=False,  # пусть модель видит контекст и сама пишет ответ
    )
