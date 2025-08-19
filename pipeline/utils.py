from typing import Any, Callable, Optional, Dict

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain.tools import StructuredTool

from pipeline.logging import logger


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
        get_raw_user_input: Callable[[], Optional[str]]
):
    """
    Возвращает корректный LangChain StructuredTool, который:
    1) логирует исходный инпут,
    2) подменяет kwargs['query'] на сырое сообщение пользователя,
    3) вызывает оригинальный MCP-инструмент (async).
    """

    # Возьмём схему аргументов из оригинального инструмента, если есть.
    # Если нет — подставим «универсальную» схему
    # с полем query и разрешением extra.
    args_schema = getattr(orig_tool, 'args_schema', None)
    if args_schema is None:
        class _Args(BaseModel):
            query: str = Field(description='Search query string')

            # Позволяем передавать любые дополнительные поля
            class Config:
                extra = 'allow'
        args_schema = _Args

    async def _acall(**kwargs: Dict[str, Any]) -> Any:
        raw = get_raw_user_input()
        # логируем ДО правки
        try:
            logger.info(
                '🔎 [ПОИСК] До правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        if raw:
            # подменяем только поле query, всё остальное сохраняем
            kwargs = {**kwargs, 'query': raw}

        # логируем ПОСЛЕ правки
        try:
            logger.info(
                '🔎 [ПОИСК] После правки | tool=%s | input=%r',
                orig_tool.name,
                kwargs
                )
        except Exception:
            pass

        # корректно дергаем оригинальный инструмент (async)
        return await orig_tool.ainvoke(kwargs)

    # Собираем корректный Tool
    wrapped = StructuredTool.from_function(
        coroutine=_acall,
        name=orig_tool.name,
        description=getattr(orig_tool, 'description', ''),
        args_schema=args_schema,
        return_direct=False,
    )
    return wrapped
