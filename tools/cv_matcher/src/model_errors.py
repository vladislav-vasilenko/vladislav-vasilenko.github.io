"""Public diagnostics never include the SDK exception text, headers or credential values."""
def model_error(error):
 status=getattr(error,'status_code',None)
 if status==401:return 'OpenAI: ключ не проходит авторизацию (401). Обновите OPENAI_API_KEY в локальном .env и перезапустите сервис и Telegram-бота. Ключ в чат присылать не нужно.'
 if status in (403,404):return 'OpenAI: модель недоступна этому проекту (HTTP '+str(status)+'). Проверьте доступ и настройку модели. Запрос автоматически не повторяется.'
 if status==429:return 'OpenAI: превышен лимит запросов или недоступна квота (429). Проверьте лимиты проекта. Автоматического платного повтора нет.'
 if status==400:return 'OpenAI отклонил параметры запроса (400). Нужно проверить ID и возможности модели; автоматического повтора нет.'
 return 'Модель не ответила. Сообщение сохранено; автоматических платных повторов нет.'
