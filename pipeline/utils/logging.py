import sys

from loguru import logger


# убираем дефолтные хендлеры (чтобы не дублировался вывод)
logger.remove()

# вывод в stdout
logger.add(
    sys.stdout,
    format='<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
           '<level>{level: <8}</level> | '
           '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
           '<level>{message}</level>',
    level='INFO'
)

# вывод в файл с ротацией
logger.add(
    'logs/app.log',
    rotation='10 MB',     # можно '1 day'
    retention='7 days',   # хранить неделю
    compression='zip',    # архивировать старые логи
    level='DEBUG',
    encoding='utf-8'
)
