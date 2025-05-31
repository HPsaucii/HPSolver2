# train_char_cnn.py
import os
import numpy as np
from tensorflow import keras
from PIL import Image

IMG_DIR = "all_chars"
LABEL_FILE = "char_labels.csv"
LABELS = "0123456789!@#$%^&*()@%"
label2idx = {c: i for i, c in enumerate(LABELS)}

# Load data
X, y = [], []
with open(LABEL_FILE) as f:
    for line in f:
        fname, label = line.strip().split(",")
        if label not in label2idx:
            continue
        img = Image.open(os.path.join(IMG_DIR, fname)).convert("L").resize((32, 32), Image.NEAREST)
        arr = np.array(img) / 255.0
        X.append(arr)
        y.append(label2idx[label])
X = np.array(X)[..., None]  # shape: (N, 32, 32, 1)
y = keras.utils.to_categorical(y, num_classes=len(LABELS))

# Model
model = keras.Sequential([
    keras.Input(shape=(32,32,1)),
    keras.layers.Conv2D(16, (3,3), activation="relu"),
    keras.layers.MaxPooling2D(),
    keras.layers.Conv2D(32, (3,3), activation="relu"),
    keras.layers.MaxPooling2D(),
    keras.layers.Flatten(),
    keras.layers.Dense(64, activation="relu"),
    keras.layers.Dense(len(LABELS), activation="softmax")
])
model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
model.fit(X, y, epochs=15, batch_size=32, validation_split=0.1)
model.save("char_cnn.keras")
