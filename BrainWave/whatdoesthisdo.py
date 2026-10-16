import cv2
import numpy as np 
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_DIR_IMAGE = os.path.join(BASE_DIR, "cleaned/Training/pituitary/Tr-pi_1.jpg")

def claheVisualizer(image):
    """
    Visualizes the effect of CLAHE (Contrast Limited Adaptive Histogram Equalization) on an image.
    CLAHE is a technique used to improve the contrast of images, especially in medical imaging. Which is useful for 
    enhancing the visibility of features in MRI scans.
    Args:
        image (numpy.ndarray): The input image to be processed.

    Returns:
        tuple: A tuple containing the original image and the CLAHE-processed image.
    """
    # Create a CLAHE object with default parameters
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    
    # Convert the image to grayscale if it is not already
    if len(image.shape) == 3 and image.shape[2] == 3:
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray_image = image
    
    # Apply CLAHE to the grayscale image
    clahe_image = clahe.apply(gray_image)
    
    return gray_image, clahe_image

def show_images(original, processed):
    """
    Displays the original and processed images side by side.

    Args:
        original (numpy.ndarray): The original image.
        processed (numpy.ndarray): The processed image.
    """
    # Stack the images horizontally
    combined_image = np.hstack((original, processed))
    
    # Display the combined image
    cv2.imshow('Original and CLAHE Processed Images', combined_image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()



if __name__ == "__main__":
    # Example usage
    image_path = TRAIN_DIR_IMAGE
    image = cv2.imread(image_path)
    
    original, clahe_processed = claheVisualizer(image)
    show_images(original, clahe_processed)
