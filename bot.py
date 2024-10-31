import logging
import vk_api
import requests
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown
from PIL import Image
from io import BytesIO
import torch
from torchvision import transforms
from torchvision.models import resnet18
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

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
image_data = []

model = resnet18(weights='DEFAULT')
model.eval()
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def get_image_vector(image_url):
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content)).convert("RGB")
    image = transform(image).unsqueeze(0)
    
    with torch.no_grad():
        vector = model(image).numpy()
    
    return vector.flatten()

def get_image_url_from_post(post_text):
    image_url_pattern = r'(https?://[^\s]+?\.(?:jpg|jpeg|png|gif))'
    matches = re.findall(image_url_pattern, post_text)
    return matches[0] if matches else None

def get_posts_from_groups(count=5000):
    all_posts = []
    for group_name, group_id, city in groups:
        try:
            logger.info(f"Получение постов из группы {group_name} (ID: {group_id})...")
            response = vk.wall.get(owner_id=-int(group_id), count=count)
            logger.info(f"Получено {len(response['items'])} постов из группы {group_name}.")
            for post in response['items']:
                image_url = get_image_url_from_post(post['text'])
                if image_url:
                    vector = get_image_vector(image_url)
                    post['image_url'] = image_url
                    all_posts.append((group_name, post, city, vector))
        except vk_api.exceptions.ApiError as e:
            logger.error("Ошибка при обращении к VK API для группы %s: %s", group_name, e)
    return all_posts

async def send_similar_posts(update: Update, photo_vector: np.ndarray):
    similar_posts = []
    
    for (group_name, post, city, vector) in image_data:
        similarity = cosine_similarity([photo_vector], [vector])
        if similarity >= 0.8:  
            similar_posts.append((group_name, post, city, similarity[0][0]))
    
    if similar_posts:
        for group_name, post, city, similarity in similar_posts:
            text = escape_markdown(post['text'], version=2)
            post_id = post['id']
            group_id = groups[current_index][1]
            post_link = f"https://vk.com/wall-{group_id}_{post_id}"
            post_info = (
                f"Группа: {escape_markdown(group_name, version=2)}\n"
                f"Город: {escape_markdown(city, version=2)}\n"
                f"Схожесть: {similarity:.2%}\n"
                f"Ссылка на пост: {post_link}\n"
                f"Текст поста: {text}"
            )
            await update.message.reply_text(post_info)
    else:
        await update.message.reply_text("Похожие посты не найдены.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    photo_url = photo_file.file_path
    
    photo_vector = get_image_vector(photo_url)
    
    await send_similar_posts(update, photo_vector)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global posts, current_index, image_data
    await update.message.reply_text("Идет поиск постов, пожалуйста, ожидайте...")
    posts = get_posts_from_groups(count=5000)
    image_data = [post[3] for post in posts]  # Получаем только векторы
    current_index = 0

def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

if __name__ == '__main__':
    main()
