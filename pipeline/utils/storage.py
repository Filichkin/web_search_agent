import json
from datetime import datetime
from typing import Any

from pipeline.utils.logging import logger


def save_search_results(
        query: str,
        results: Any,
        output_file='results.json',
        max_items: int = 5
) -> int:
    items = []
    now = datetime.now().isoformat(timespec='seconds')

    # results = list of JSON strings
    if isinstance(results, list):
        for el in results[:max_items]:
            try:
                if isinstance(el, str):
                    data = json.loads(el)
                elif isinstance(el, dict):
                    data = el
                else:
                    continue

                url = (data.get('url') or '').strip()
                title = (data.get('title') or '').strip()
                description = (data.get('description') or '').strip()

                items.append({
                    "query": query,
                    "date": now,
                    "title": title,
                    "description": description,
                    "url": url
                })
            except Exception as e:
                logger.error(f'⚠️ Ошибка парсинга элемента: {e}')

    # читаем уже сохранённое
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = []
    except (FileNotFoundError, json.JSONDecodeError):
        data = []

    data.extend(items)

    # сохраняем
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return len(items)
