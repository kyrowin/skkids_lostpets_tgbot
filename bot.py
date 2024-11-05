import logging
import vk_api
import requests
from bs4 import BeautifulSoup
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.helpers import escape_markdown
from PIL import Image
from io import BytesIO
import torch
from torchvision import transforms
from torchvision.models import resnet50
import numpy as np
from scipy.spatial.distance import cosine  # Импортируем косинусное расстояние

VK_API_TOKEN = 'd78e593cd78e593cd78e593cb9d4ac02dddd78ed78e593cb0afbaaeab5a89d75de7db1d'
TELEGRAM_BOT_TOKEN = '7582841082:AAGoI62LcnGQxPdEHkkZ-F55CmqW3AVKhXY'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s', level=logging.INFO)
logger = logging.getLogger(__name__)

search_keywords = ['нашел', 'нашла', 'на улице', 'пропал', 'потеряшка']

groups = [
    ("lostpets", "39991594", "Вологодская обл."),
    ("public183021083", "183021083", "Тобольск"),
]

vk_session = vk_api.VkApi(token=VK_API_TOKEN)
vk = vk_session.get_api()

posts = []
current_index = 0

# Загружаем модель ResNet50 для классификации изображений
model = resnet50(weights='DEFAULT')
model.eval()

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

# Классификация изображений
def classify_image(image_url):
    image_vector = get_image_vector(image_url)
    if image_vector is None:
        return 'Неизвестно'
    return 'Собака' if image_vector is not None else 'Неизвестно'

# Получение вектора изображения
def get_image_vector(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image = transform(image).unsqueeze(0)

        with torch.no_grad():
            vector = model(image).numpy()

        return vector.flatten()
    except Exception as e:
        logger.error("Ошибка при получении вектора изображения: %s", e)
        return None

# Получение ссылок на изображения из постов
def get_image_url_from_post(post_text):
    soup = BeautifulSoup(post_text, "html.parser")
    img_tags = soup.find_all("img")
    if img_tags:
        return img_tags[0]["src"]
    return None

# Получение постов из групп
def get_posts_from_groups(count=5000):
    all_posts = []
    for group_name, group_id, city in groups:
        try:
            response = vk.wall.get(owner_id=-int(group_id), count=count)
            for post in response['items']:
                if 'attachments' in post:
                    for attachment in post['attachments']:
                        if attachment['type'] == 'photo':
                            image_url = attachment['photo']['sizes'][-1]['url']
                            break
                    else:
                        image_url = None
                else:
                    image_url = None

                animal_type = classify_image(image_url) if image_url else 'Неизвестно'
                if image_url or any(keyword in post['text'].lower() for keyword in search_keywords):
                    post['animal_type'] = animal_type
                    post['image_url'] = image_url
                    all_posts.append((group_name, post, city))
        except vk_api.exceptions.ApiError as e:
            logger.error("Ошибка при обращении к VK API для группы %s: %s", group_name, e)
    return all_posts

async def send_post(update: Update):
    global current_index
    if current_index < len(posts):
        post = posts[current_index]
        text = escape_markdown(post[1]['text'], version=2)
        post_id = post[1]['id']
        group_id = groups[current_index][1]
        post_link = f"https://vk.com/wall-{group_id}_{post_id}"

        media = []
        if post[1].get('image_url'):
            media.append(InputMediaPhoto(media=post[1]['image_url'], caption=text))
        else:
            await update.message.reply_text("Пост без изображения.")
            return  # Прерываем выполнение, если нет изображения

        # Кнопки навигации
        keyboard = []
        if current_index > 0:
            keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='previous')])
        if current_index < len(posts) - 1:
            keyboard.append([InlineKeyboardButton("Вперёд ➡️", callback_data='next')])
        keyboard.append([InlineKeyboardButton("Открыть пост", url=post_link)])
        keyboard.append([InlineKeyboardButton(f"Тип животного: {post[1].get('animal_type', 'Неизвестно')}", callback_data='no_action')])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Здесь используем update.message для отправки медиа-группы
        await update.message.reply_media_group(media)
        await update.message.reply_text(f"Тип животного: {post[1].get('animal_type', 'Неизвестно')}", reply_markup=reply_markup)

    else:
        await update.message.reply_text("Не найдено больше постов.")

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_index
    query = update.callback_query
    await query.answer()

    if query.data == 'next':
        current_index += 1
        await send_post(query)  # Изменено для передачи объекта query
    elif query.data == 'previous':
        if current_index > 0:
            current_index -= 1
        await send_post(query)  # Изменено для передачи объекта query

# Обработка фотографий
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_url = photo_file.file_path
    photo_vector = get_image_vector(photo_url)

    if photo_vector is not None:
        await send_similar_posts(update, photo_url)  # Изменено для передачи URL изображения
    else:
        await update.message.reply_text("Не удалось обработать загруженное изображение.")

# Поиск похожих постов
async def send_similar_posts(update: Update, photo_url):
    global current_index
    similar_posts = []
    
    # Получаем вектор изображения пользователя
    user_vector = get_image_vector(photo_url)

    if user_vector is None:
        await update.message.reply_text("Не удалось получить вектор для загруженного изображения.")
        return

    for post in posts:
        post_vector = get_image_vector(post[1]['image_url'])
        if post_vector is not None:
            # Сравниваем векторы, используя косинусное расстояние
            distance = cosine(user_vector, post_vector)
            logger.info(f"Сравнение изображений: расстояние {distance}")

            if distance < 0.1:  # Порог для схожести
                similar_posts.append(post)

    if similar_posts:
        await update.message.reply_text("Найдено похожих постов:")
        for post in similar_posts:
            # Обновляем индекс, чтобы не было дублирования
            current_index = posts.index(post)
            await send_post(update)
    else:
        await update.message.reply_text("Похожие посты не найдены.")

# Команда старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global posts, current_index
    await update.message.reply_text("Идет поиск постов, пожалуйста, ожидайте... Это занимает до 30 секунд.")
    posts = get_posts_from_groups(count=5000)
    current_index = 0
    await send_post(update)

# Обработка кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_index
    query = update.callback_query
    await query.answer()

    if query.data == 'next':
        current_index += 1
        await send_post(query.message)
    elif query.data == 'previous':
        if current_index > 0:
            current_index -= 1
        await send_post(query.message)

# Основная функция
def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == '__main__':
    main()
