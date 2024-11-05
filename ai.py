import numpy as np
import tensorflow as tf
from tensorflow.keras.applications import VGG16
from tensorflow.keras.applications.vgg16 import preprocess_input
from tensorflow.keras.preprocessing import image

# Загружаем предобученную модель VGG16
model = VGG16(weights='imagenet', include_top=False, pooling='avg')

def get_image_vector(img_path):
    # Загружаем изображение и изменяем его размер
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    img_array = np.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)

    # Получаем вектор признаков
    vector = model.predict(img_array)
    return vector.flatten()  # Приводим к одномерному массиву

# Пример использования
cat_vector = get_image_vector("path_to_your_cat_image.jpg")
dog_vector = get_image_vector("path_to_your_dog_image.jpg")

# Сохраняем векторы в файл для дальнейшего использования
np.save("cat_vector.npy", cat_vector)
np.save("dog_vector.npy", dog_vector)
