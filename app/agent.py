# run_gradio_agent.py
import os
import gradio as gr

from dotenv import load_dotenv

from config import settings
from app.main import FileSystemAgent, AgentConfig, ModelProvider
from app.utils.logging import logger


_agent_holder: dict[str, FileSystemAgent | None] = {'agent': None}


async def _startup():
    if _agent_holder['agent'] and _agent_holder['agent'].is_ready:
        return '✅ Агент уже инициализирован'

    load_dotenv()
    cfg = AgentConfig(
        filesystem_path=settings.FILESYSTEM_PATH,
        model_provider=ModelProvider(settings.MODEL_PROVIDER),
        enable_web_search=True
    )
    agent = FileSystemAgent(cfg)
    ok = await agent.initialize()
    if not ok:
        logger.error('❌ Не удалось инициализировать агента')
        return '❌ Не удалось инициализировать агента'
    _agent_holder['agent'] = agent
    logger.info('✅ Агент готов (Gradio)')
    return '✅ Агент готов'


# --- Обработчик сообщений чата (асинхронный) ---
async def chat_handler(message: str, history: list[dict]):
    if not _agent_holder['agent'] or not _agent_holder['agent'].is_ready:
        init_msg = await _startup()
        logger.info(init_msg)

    agent = _agent_holder['agent']
    try:
        reply = await agent.process_message(message, thread_id='gradio')
        return reply
    except Exception as e:
        logger.error(f'❌ Ошибка обработки: {e}')
        return (
            '❌ Не удалось сгенерировать ответ. '
            'Попробуйте ещё раз или проверьте логи.'
        )


# --- Кнопка статуса агента ---
async def get_status():
    if not _agent_holder['agent'] or not _agent_holder['agent'].is_ready:
        init_msg = await _startup()
        if '❌' in init_msg:
            return 'Агент не инициализирован.'
    agent = _agent_holder['agent']
    st = agent.get_status()
    lines = [
        f'initialized: {st.get("initialized")}',
        f'model_provider: {st.get("model_provider")}',
        f'filesystem_path: {st.get("filesystem_path")}',
        f'memory_enabled: {st.get("memory_enabled")}',
        f'web_search_enabled: {st.get("web_search_enabled")}',
        f'tools_count: {st.get("tools_count")}',
        f'brave_api_key_present: {st.get("brave_api_key_present")}',
    ]
    return '\n'.join(lines)


# --- Сборка Gradio UI ---
def build_app() -> gr.Blocks:
    with gr.Blocks(title='Web Search Agent', theme='soft') as demo:
        header = gr.Markdown('# 🔍 Web Search Agent')
        sub = gr.Markdown(
            'Задавайте вопросы — агент выполнит веб-поиск (Brave MCP), '
            'обогатит источники и вернёт развёрнутый ответ.'
        )

        chat = gr.Chatbot(height=800, type='messages', show_copy_button=True)
        msg = gr.Textbox(
            label='Ваш запрос',
            placeholder=(
                'Например: Какие главные инсайты по GEO за последний месяц?'
                ),
            autofocus=True
        )
        send = gr.Button('Отправить', variant='primary')
        clear = gr.Button('Очистить чат')

        with gr.Row():
            status_btn = gr.Button('Статус агента')
        status_out = gr.Textbox(label='Статус', interactive=False)

        # инициализация при загрузке приложения
        init_status = gr.Markdown('⏳ Инициализация...')
        demo.load(_startup, inputs=None, outputs=init_status)

        # обработка отправки
        async def _on_send(user_text, history):
            reply = await chat_handler(user_text, history or [])
            new_history = (history or []) + [
                {'role': 'user', 'content': user_text},
                {'role': 'assistant', 'content': reply},
            ]
            return '', new_history

        send.click(_on_send, inputs=[msg, chat], outputs=[msg, chat])
        msg.submit(_on_send, inputs=[msg, chat], outputs=[msg, chat])

        # очистка чата
        def _clear_chat():
            return []

        clear.click(_clear_chat, inputs=None, outputs=chat)

        # статус
        status_btn.click(get_status, inputs=None, outputs=status_out)

    return demo


if __name__ == '__main__':
    port = int(os.getenv('PORT', '7860'))
    app = build_app()
    # просто включаем очередь
    app.queue().launch(
        server_name='0.0.0.0',
        server_port=port,
        show_error=True
    )
