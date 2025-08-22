import json
from datetime import datetime
from typing import Any

from pipeline.utils.logging import logger


def save_search_results(
    query: str,
    results: Any,
    output_file: str = 'results.json',
    max_items: int = 5,
    already_enriched: bool = False
) -> int:
    now = datetime.now().isoformat(timespec='seconds')

    logger.info(
        '💾 Сохранение результатов поиска: query={!r}, '
        'макс. элементов={}, файл={!r}, enriched={}',
        query, max_items, output_file, already_enriched
    )

    # читаем существующие данные
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                logger.warning(
                    'Файл {} не является списком, перезаписываем',
                    output_file
                    )
                data = []
    except FileNotFoundError:
        logger.info('Файл {} не найден, создаём новый', output_file)
        data = []
    except json.JSONDecodeError:
        logger.warning(
            'Файл {} повреждён или пустой, перезаписываем',
            output_file
            )
        data = []

    # множество уже существующих ключей для дедупа
    existing_urls = {
        (rec.get('url') or '').strip().lower()
        for rec in data if isinstance(rec, dict)
    }

    added = 0

    if already_enriched:
        # ожидаем список словарей {'url','title','snippet'}
        if isinstance(results, list):
            logger.info('Получено {} enriched-элементов, берём первые {}',
                        len(results), min(len(results), max_items))
            for index, element in enumerate(results[:max_items], start=1):
                url = (element.get('url') or '').strip()
                url_key = url.lower()
                if not url or url_key in existing_urls:
                    logger.info(
                        '[{}] Пропуск (дубликат или пустой URL): {!r}',
                        index,
                        url
                        )
                    continue
                title = (element.get('title') or '').strip() or url
                description = (element.get('snippet') or '').strip()
                data.append({
                    'query': query,
                    'date': now,
                    'title': title,
                    'description': description,
                    'url': url
                })
                existing_urls.add(url_key)
                added += 1
        else:
            logger.warning(
                'Ожидался список enriched-элементов, получено: {!r}',
                type(results)
                )
    else:
        # сырой список (строки JSON или словари)
        if isinstance(results, list):
            logger.info('Получено {} результатов, берём первые {}',
                        len(results), min(len(results), max_items))
            for index, element in enumerate(results[:max_items], start=1):
                try:
                    data_el = (
                        json.loads(element) if isinstance(element, str)
                        else element
                        )
                except Exception as error:
                    logger.warning(
                        '[{}] Не удалось распарсить элемент: {}',
                        index,
                        error
                        )
                    continue
                url = (data_el.get('url') or '').strip()
                url_key = url.lower()
                if not url or url_key in existing_urls:
                    logger.info(
                        '[{}] Пропуск (дубликат или пустой URL): {!r}',
                        index,
                        url
                        )
                    continue
                title = (data_el.get('title') or '').strip() or url
                description = (data_el.get('description') or '').strip()
                data.append({
                    'query': query,
                    'date': now,
                    'title': title,
                    'description': description,
                    'url': url
                })
                existing_urls.add(url_key)
                added += 1
        else:
            logger.warning(
                'Ожидался список сырых элементов, получено: {!r}',
                type(results)
                )

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(
        'Успешно добавлено {} новых записей (после дедупа). Всего: {}',
        added,
        len(data)
        )
    return added
