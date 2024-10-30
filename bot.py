import logging
import vk_api
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Токены
VK_API_TOKEN = 'd78e593cd78e593cd78e593cb9d4ac02dddd78ed78e593cb0afbaaeab5a89d75de7db1d'
TELEGRAM_BOT_TOKEN = '7582841082:AAGoI62LcnGQxPdEHkkZ-F55CmqW3AVKhXY'

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Группы для поиска постов
groups = [
    ("lostpets", "39991594", "Вологодская обл."),
    ("public183021083", "183021083", "Тобольск"),
]

vk_session = vk_api.VkApi(token=VK_API_TOKEN)
vk = vk_session.get_api()

posts = []
current_index = 0

def get_posts_from_groups(count=10):
    all_posts = []
    for group_name, group_id, city in groups:
        try:
            response = vk.wall.get(owner_id=-int(group_id), count=count)
            for post in response['items']:
                all_posts.append((group_name, post, city))
        except vk_api.exceptions.ApiError as e:
            logger.error("Ошибка при обращении к VK API для группы %s: %s", group_name, e)
    return all_posts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Нажмите /get_posts, чтобы получить посты из ВК.")

async def get_posts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global posts, current_index
    count = 5
    posts = get_posts_from_groups(count=count)
    current_index = 0
    await send_post(update)

async def send_post(update: Update) -> None:
    global current_index, posts
    if posts and 0 <= current_index < len(posts):
        group_name, post, city = posts[current_index]
        text = post['text']
        post_id = post['id']
        post_link = f"https://vk.com/wall-{group_name}_{post_id}"
        post_info = f"**Группа:** {group_name} (ID: {post_id})\n**Город:** {city}\n{text}"
        
        keyboard = [
            [InlineKeyboardButton("⬅", callback_data='left'), 
             InlineKeyboardButton("⮕", callback_data='right')],
            [InlineKeyboardButton("Открыть пост", url=post_link)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(post_info, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text("Постов больше нет.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_index, posts
    query = update.callback_query
    await query.answer()
    
    if query.data == 'left':
        if current_index > 0:
            current_index -= 1
            await send_post(query)
        else:
            await query.edit_message_text("Это первый пост.")
    elif query.data == 'right':
        if current_index < len(posts) - 1:
            current_index += 1
            await send_post(query)
        else:
            await query.edit_message_text("Это последний пост.")

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("get_posts", get_posts))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__ == '__main__':
    main()
