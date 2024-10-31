import logging
import vk_api
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.helpers import escape_markdown
from PIL import Image
from io import BytesIO
import torch
from torchvision import transforms
from torchvision.models import resnet18

VK_API_TOKEN = 'd78e593cd78e593cd78e593cb9d4ac02dddd78ed78e593cb0afbaaeab5a89d75de7db1d'
TELEGRAM_BOT_TOKEN = '7582841082:AAGoI62LcnGQxPdEHkkZ-F55CmqW3AVKhXY'

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

groups = [
    ("lostpets", "39991594", "Вологодская обл."),
    ("public183021083", "183021083", "Тобольск"),
]

vk_session = vk_api.VkApi(token=VK_API_TOKEN)
vk = vk_session.get_api()

posts = []
current_index = 0
last_message_id = None  # Отслеживание последнего сообщения для удаления

model = resnet18(pretrained=True)
model.eval()
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def classify_image(image_url):
    try:
        response = requests.get(image_url)
        image = Image.open(BytesIO(response.content)).convert("RGB")
        image = transform(image).unsqueeze(0)
        
        with torch.no_grad():
            output = model(image)
        
        _, predicted = output.max(1)
        return "Кошка" if predicted.item() == 0 else "Собака"
    except Exception as e:
        logger.error("Ошибка классификации изображения: %s", e)
        return "Неизвестно"

def get_image_url_from_post(post_text):
    soup = BeautifulSoup(post_text, 'html.parser')
    img_tag = soup.find('img')
    return img_tag['src'] if img_tag else None

def get_posts_from_groups(count=10):
    all_posts = []
    for group_name, group_id, city in groups:
        try:
            response = vk.wall.get(owner_id=-int(group_id), count=count)
            for post in response['items']:
                image_url = get_image_url_from_post(post['text'])
                animal_type = classify_image(image_url) if image_url else "Изображение отсутствует"
                post['animal_type'] = animal_type
                post['image_url'] = image_url  # Добавляем URL изображения в данные поста
                all_posts.append((group_name, post, city))
        except vk_api.exceptions.ApiError as e:
            logger.error("Ошибка при обращении к VK API для группы %s: %s", group_name, e)
    return all_posts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global posts, current_index
    count = 5
    posts = get_posts_from_groups(count=count)
    current_index = 0
    await send_post(update)

async def send_post(update: Update) -> None:
    global current_index, posts, last_message_id
    if posts and 0 <= current_index < len(posts):
        group_name, post, city = posts[current_index]
        text = escape_markdown(post['text'], version=2)
        post_id = post['id']
        group_id = groups[current_index][1]
        post_link = f"https://vk.com/wall-{group_id}_{post_id}"
        
        # Добавляем информацию о животном и фото
        animal_type = post.get('animal_type', 'Неизвестно')
        post_info = (
            f"Группа: {escape_markdown(group_name, version=2)}\n"
            f"Город: {escape_markdown(city, version=2)}\n"
            f"Тип животного: {escape_markdown(animal_type, version=2)}\n{text}"
        )
        
        # Удаление предыдущего сообщения
        if last_message_id:
            try:
                await update.message.bot.delete_message(update.effective_chat.id, last_message_id)
            except Exception as e:
                logger.warning("Не удалось удалить предыдущее сообщение: %s", e)

        # Кнопки
        keyboard = []
        if current_index > 0:
            keyboard.append([InlineKeyboardButton("⬅", callback_data='left')])
        if current_index < len(posts) - 1:
            if keyboard:
                keyboard[0].append(InlineKeyboardButton("⮕", callback_data='right'))
            else:
                keyboard.append([InlineKeyboardButton("⮕", callback_data='right')])
        keyboard.append([InlineKeyboardButton("Открыть пост", url=post_link)])
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправка фото вместе с текстом, если URL изображения найден
        image_url = post.get('image_url')
        if image_url:
            response = requests.get(image_url)
            image = BytesIO(response.content)
            message = await update.message.reply_photo(
                photo=image,
                caption=post_info,
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
        else:
            message = await update.message.reply_text(post_info, reply_markup=reply_markup, parse_mode='MarkdownV2')
        
        last_message_id = message.message_id  # Сохранение ID последнего сообщения
    else:
        await update.message.reply_text("Постов больше нет.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global current_index, posts
    query = update.callback_query
    await query.answer()
    
    if query.data == 'left' and current_index > 0:
        current_index -= 1
    elif query.data == 'right' and current_index < len(posts) - 1:
        current_index += 1

    await send_post(query)

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__ == '__main__':
    main()
