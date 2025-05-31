# char_predictor.py
from tensorflow import keras
import numpy as np
from PIL import Image

LABELS = "0123456789!@#$%^&*()@%"
model = keras.models.load_model("char_cnn.keras")

def predict_char(img_arr):
    # img_arr: 2D numpy array, shape (H, W), values 0-255
    arr = np.array(Image.fromarray(img_arr).resize((32,32), Image.NEAREST)) / 255.0
    arr = arr[None, ..., None]  # shape (1, 32, 32, 1)
    pred = model.predict(arr)
    idx = np.argmax(pred)
    return LABELS[idx], float(np.max(pred))
