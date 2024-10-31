import logging
import vk_api
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.helpers import escape_markdown

VK_API_TOKEN = 'd78e593cd78e593cd78e593cb9d4ac02dddd78ed78e593cb0afbaaeab5a89d75de7db1d'
TELEGRAM_BOT_TOKEN = '7582841082:AAGoI62LcnGQxPdEHkkZ-F55CmqW3AVKhXY'

# Список слов для поиска
SEARCH_TERMS = ["потеря", "питомец", "собака", "кошка", "ищем", "помогите", "найден", "пропал"]

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Указываем только группу lostpets
groups = [
    ("lostpets", "39991594", "Вологодская обл."),
]

vk_session = vk_api.VkApi(token=VK_API_TOKEN)
vk = vk_session.get_api()

posts = []
current_index = 0

def get_posts_from_groups(count=100):  # Установите лимит по умолчанию
    all_posts = []
    for group_name, group_id, city in groups:
        try:
            logger.info("Получение постов из группы %s (ID: %s)...", group_name, group_id)
            response = vk.wall.get(owner_id=-int(group_id), count=count)
            for post in response['items']:
                if 'text' in post and post['text']:  # Убедитесь, что текст поста существует
                    logger.debug("Текст поста: %s", post['text'])  # Логируем текст поста
                    # Проверяем, есть ли ключевые слова в тексте поста
                    if any(term in post['text'].lower() for term in SEARCH_TERMS):
                        all_posts.append((group_name, post, city))  # Сохраняем только посты
                        logger.info("Найден подходящий пост: %s", post['text'])
            logger.info("Получено %d постов из группы %s.", len(response['items']), group_name)
        except vk_api.exceptions.ApiError as e:
            logger.error("Ошибка при обращении к VK API для группы %s: %s", group_name, e)
    return all_posts

async def send_found_posts(update: Update, found_posts):
    if found_posts:
        for group_name, post, city in found_posts:
            text = escape_markdown(post['text'], version=2)
            post_id = post['id']
            group_id = groups[current_index][1]
            post_link = f"https://vk.com/wall-{group_id}_{post_id}"
            post_info = (
                f"Группа: {escape_markdown(group_name, version=2)}\n"
                f"Город: {escape_markdown(city, version=2)}\n"
                f"Ссылка на пост: {post_link}\n"
                f"Текст: {text}"
            )
            await update.message.reply_text(post_info)
    else:
        await update.message.reply_text("Подходящие посты не найдены.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Идет поиск постов, пожалуйста, ожидайте...")
    found_posts = get_posts_from_groups(count=100)  # Поиск только в lostpets
    logger.info("Всего найдено постов: %d", len(found_posts))
    
    # Отправляем найденные посты
    await send_found_posts(update, found_posts)

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == '__main__':
    main()
