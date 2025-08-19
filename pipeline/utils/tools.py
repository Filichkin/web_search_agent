from typing import Any, Callable, Optional, Dict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.tools import StructuredTool

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
        max_calls_per_message: int = 2   # ← ограничение для одного сообщения
):
    """
    StructuredTool-обёртка:
    - логирует вход,
    - подменяет kwargs['query'] на сырое сообщение пользователя,
    - защищает от повторов и бесконечной петли,
    - сохраняет сырые результаты в JSON.
    (Без вмешательства в count/limit/и т.п.)
    """

    # состояние «на текущее сообщение»
    called_queries: set[str] = set()
    call_count: int = 0
    last_seen_raw: Optional[str] = None

    # схема аргументов (как у тебя было)
    args_schema = getattr(orig_tool, 'args_schema', None)
    if args_schema is None:
        class _Args(BaseModel):
            query: str = Field(description='Search query string')

            class Config:
                extra = 'allow'
        args_schema = _Args

    async def _acall(**kwargs: Dict[str, Any]) -> Any:
        nonlocal call_count, called_queries, last_seen_raw

        raw = get_raw_user_input()

        # если пришёл новый пользовательский ввод — сбросить состояние
        if raw != last_seen_raw:
            called_queries = set()
            call_count = 0
            last_seen_raw = raw

        # лог ДО правки
        try:
            logger.info(
                '🔎 [ПОИСК] До правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        # подменяем только query (остальное не трогаем)
        if raw:
            kwargs = {**kwargs, 'query': raw}

        # анти-петля: дедуп + лимит
        qnorm = (kwargs.get('query') or '').strip().lower()
        if qnorm in called_queries:
            return (
                'Поиск уже выполнен по этому же запросу; '
                'используй найденные ссылки/результаты для ответа.'
                )
        if call_count >= max_calls_per_message:
            return (
                'Достигнут лимит поисковых запросов для этого сообщения; '
                'сформируй ответ по имеющимся результатам.'
                )
        called_queries.add(qnorm)
        call_count += 1

        # лог ПОСЛЕ правки
        try:
            logger.info(
                '🔎 [ПОИСК] После правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        result = await orig_tool.ainvoke(kwargs)
        logger.info(result)

        # сохраняем результаты
        try:
            query = kwargs.get('query', '')
            save_search_results(query, result)
            logger.info('Успешно сохранено')
        except Exception as e:
            logger.warning('Не удалось сохранить результаты поиска: %s', e)

        return result

    return StructuredTool.from_function(
        coroutine=_acall,
        name=orig_tool.name,
        description=getattr(orig_tool, 'description', ''),
        args_schema=args_schema,
        return_direct=False,
    )
