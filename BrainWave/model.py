import os
import tensorflow as tf
from tensorflow import keras

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_DIR = os.path.join(BASE_DIR, "cleaned/Training")
TEST_DIR = os.path.join(BASE_DIR, "cleaned/Testing")

IMG_SIZE = 256
BATCH_SIZE = 32
EPOCHS_FROZEN = 10
EPOCHS_FINETUNE = 10

# ── Data loading ──────────────────────────────────────────────────────────────

train_ds = keras.utils.image_dataset_from_directory(
    TRAIN_DIR,
    validation_split=0.2,
    subset="training",
    seed=42,
    image_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
)

val_ds = keras.utils.image_dataset_from_directory(
    TRAIN_DIR,
    validation_split=0.2,
    subset="validation",
    seed=42,
    image_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
)

test_ds = keras.utils.image_dataset_from_directory(
    TEST_DIR,
    image_size=(IMG_SIZE, IMG_SIZE),
    batch_size=BATCH_SIZE,
    shuffle=False,
)

class_names = train_ds.class_names
print("Classes:", class_names)

AUTOTUNE = tf.data.AUTOTUNE
train_ds = train_ds.cache().shuffle(1000).prefetch(AUTOTUNE)
val_ds = val_ds.cache().prefetch(AUTOTUNE)
test_ds = test_ds.cache().prefetch(AUTOTUNE)

# ── Augmentation ──────────────────────────────────────────────────────────────

augment = keras.Sequential([
    keras.layers.RandomFlip("horizontal"),
    keras.layers.RandomRotation(0.1),
    keras.layers.RandomZoom(0.1),
], name="augmentation")

# ── Model ─────────────────────────────────────────────────────────────────────

base_model = keras.applications.EfficientNetB0(
    include_top=False,
    weights="imagenet",
    input_shape=(IMG_SIZE, IMG_SIZE, 3),
)
base_model.trainable = False  # freeze pretrained weights for first training phase

inputs = keras.Input(shape=(IMG_SIZE, IMG_SIZE, 3))
x = augment(inputs)
# EfficientNetB0 expects pixel values in [0, 255]; no manual rescaling needed
x = base_model(x, training=False)
x = keras.layers.GlobalAveragePooling2D()(x)
x = keras.layers.Dense(128, activation="relu")(x)
x = keras.layers.Dropout(0.3)(x)
outputs = keras.layers.Dense(len(class_names), activation="softmax")(x)

model = keras.Model(inputs, outputs)
model.summary()

# ── Phase 1: train classification head ────────────────────────────────────────

model.compile(
    optimizer=keras.optimizers.Adam(1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

history = model.fit(
    train_ds,
    epochs=EPOCHS_FROZEN,
    validation_data=val_ds,
    callbacks=[
        keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True),
    ],
)

# ── Phase 2: fine-tune top layers of base model ───────────────────────────────

base_model.trainable = True
# only unfreeze the last 20 layers
for layer in base_model.layers[:-20]:
    layer.trainable = False

model.compile(
    optimizer=keras.optimizers.Adam(1e-5),  # lower LR to avoid destroying pretrained weights
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

history_finetune = model.fit(
    train_ds,
    epochs=EPOCHS_FINETUNE,
    validation_data=val_ds,
    callbacks=[
        keras.callbacks.EarlyStopping(patience=3, restore_best_weights=True),
    ],
)

# ── Evaluate ──────────────────────────────────────────────────────────────────

loss, accuracy = model.evaluate(test_ds)
print(f"\nTest accuracy: {accuracy:.4f}")

model.save(os.path.join(BASE_DIR, "brainwave_model.keras"))
print("Model saved to brainwave_model.keras")
