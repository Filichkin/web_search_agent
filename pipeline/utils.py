from langchain_core.callbacks import BaseCallbackHandler

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
