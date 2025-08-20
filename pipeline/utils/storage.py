import json
from datetime import datetime
from typing import Any

from pipeline.utils.content import fetch_desc_trafilatura
from pipeline.utils.logging import logger


def save_search_results(
        query: str,
        results: Any,
        output_file='results.json',
        max_items: int = 5
) -> int:
    items = []
    now = datetime.now().isoformat(timespec='seconds')

    logger.info(f'💾 Сохранение результатов поиска: query="{query}", '
                f'макс. элементов={max_items}, файл="{output_file}"')

    if isinstance(results, list):
        logger.info(
            f'Получено {len(results)} результатов, '
            f'берём первые {min(len(results), max_items)}'
            )

        for item, element in enumerate(results[:max_items], start=1):
            try:
                data = json.loads(element) if isinstance(
                    element, str) else element
            except Exception as e:
                logger.warning(
                    f'[{item}] Не удалось распарсить элемент: {element}, '
                    f'ошибка: {e}'
                    )
                continue

            url = (data.get('url') or '').strip()
            title = (data.get('title') or '').strip()
            description = (data.get('description') or '').strip()

            logger.info(f'[{item}] URL="{url}", title="{title}", '
                        f'description={"есть" if description else "пусто"}')

            # 🔸 Если описания нет — пробуем выжать его Trafilatura
            logger.info(
                f'[{item}] Пытаемся извлечь описание через Trafilatura '
                f'для {url or "<no-url>"}'
                )
            new_description = fetch_desc_trafilatura(
                url,
                fallback_text=description,
                max_chars=1000
            )

            if new_description and new_description != description:
                snippet = new_description[:200].replace('\n', ' ')
                logger.info(
                    f'[{item}] Trafilatura извлекла описание '
                    f'({len(new_description)} символов): "{snippet}..."'
                    )
            elif new_description:
                logger.info(f'[{item}] Используем fallback из результата '
                            f'поиска ({len(new_description)} символов)'
                            )
            else:
                logger.warning(
                    f'[{item}] Описание отсутствует '
                    f'даже после Trafilatura и fallback'
                    )

            description = new_description

            items.append({
                'query': query,
                'date': now,
                'title': title,
                'description': description,
                'url': url
            })

    # читаем уже сохранённое
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                logger.warning(
                    f'Файл {output_file} не является списком, перезаписываем'
                    )
                data = []
    except FileNotFoundError:
        logger.info(f'Файл {output_file} не найден, создаём новый')
        data = []
    except json.JSONDecodeError:
        logger.warning(
            f'Файл {output_file} повреждён или пустой, перезаписываем'
            )
        data = []

    data.extend(items)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f'Успешно сохранено {len(items)} новых результатов. '
                f'Всего в файле теперь {len(data)} записей.')

    return len(items)
