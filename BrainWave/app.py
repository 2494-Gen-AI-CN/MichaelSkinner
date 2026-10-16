import os
import cv2
import numpy as np
import tensorflow as tf
from tensorflow import keras
import gradio as gr
from preproccessing import crop_img

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "brainwave_model.keras")

CLASS_NAMES = ["Glioma", "Meningioma", "No Tumor", "Pituitary"]
IMG_SIZE = 256

model = keras.models.load_model(MODEL_PATH)


def predict(image):
    print(f"[DEBUG] Input shape: {image.shape}, dtype: {image.dtype}, min: {image.min()}, max: {image.max()}")
    try:
        cropped = crop_img(image)
        print(f"[DEBUG] Crop succeeded: {cropped.shape}")
        image = cropped
    except Exception as e:
        print(f"[DEBUG] Crop failed: {e} — using raw image")

    img = tf.image.resize(image, (IMG_SIZE, IMG_SIZE))
    img = tf.expand_dims(img, axis=0)
    probs = model.predict(img, verbose=0)[0]
    print(f"[DEBUG] Probs: { {CLASS_NAMES[i]: f'{probs[i]:.3f}' for i in range(len(CLASS_NAMES))} }")
    return {CLASS_NAMES[i]: float(probs[i]) for i in range(len(CLASS_NAMES))}


demo = gr.Interface(
    fn=predict,
    inputs=gr.Image(type="numpy", label="Upload MRI scan"),
    outputs=gr.Label(num_top_classes=4, label="Prediction"),
    title="BrainWave — Brain Tumor MRI Classifier",
    description="Upload a brain MRI scan and the model will classify it as Glioma, Meningioma, No Tumor, or Pituitary.",
    examples=[],
    flagging_mode="never",
)

if __name__ == "__main__":
    demo.launch(show_error=True)
