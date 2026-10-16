"""
This script is used to crop the images in the dataset to remove the background and keep only the
Github: tumor region. It uses OpenCV to find the contours of the tumor and crop the image accordingly.
Github: https://github.com/masoudnick/Brain-Tumor-MRI-Classification
"""

import os

import cv2
import imutils 
import numpy as np
from tqdm import tqdm


def crop_img(img):
	"""
	Finds the extreme points on the image and crops the rectangular out of them
	"""
	gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
	gray = cv2.GaussianBlur(gray, (3, 3), 0)

	# threshold the image, then perform a series of erosions +
	# dilations to remove any small regions of noise
	thresh = cv2.threshold(gray, 45, 255, cv2.THRESH_BINARY)[1]
	thresh = cv2.erode(thresh, None, iterations=2)
	thresh = cv2.dilate(thresh, None, iterations=2)

	# find contours in thresholded image, then grab the largest one
	cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
	cnts = imutils.grab_contours(cnts)
	c = max(cnts, key=cv2.contourArea)

	# find the extreme points
	extLeft = tuple(c[c[:, :, 0].argmin()][0])
	extRight = tuple(c[c[:, :, 0].argmax()][0])
	extTop = tuple(c[c[:, :, 1].argmin()][0])
	extBot = tuple(c[c[:, :, 1].argmax()][0])
	ADD_PIXELS = 0
	new_img = img[extTop[1]-ADD_PIXELS:extBot[1]+ADD_PIXELS, extLeft[0]-ADD_PIXELS:extRight[0]+ADD_PIXELS].copy()

	return new_img


def normalize_contrast(img):
	"""
	Applies CLAHE to the L channel of the image to standardize contrast across
	different scanners and sources, forcing the model to learn structural features
	rather than brightness-based shortcuts.
	"""
	img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
	lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
	clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
	lab[:, :, 0] = clahe.apply(lab[:, :, 0])
	img_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
	return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
	
if __name__ == "__main__":
	BASE_DIR = os.path.dirname(os.path.abspath(__file__))
	training = os.path.join(BASE_DIR, "dataset/Training")
	testing = os.path.join(BASE_DIR, "dataset/Testing")
	training_dir = os.listdir(training)
	testing_dir = os.listdir(testing)
	IMG_SIZE = 256

	for dir in training_dir:
		save_path = os.path.join(BASE_DIR, 'cleaned/Training/'+ dir)
		path = os.path.join(training,dir)
		image_dir = os.listdir(path)
		for img in image_dir:
			image = cv2.imread(os.path.join(path,img))
			image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
			new_img = crop_img(image_rgb)
			new_img = normalize_contrast(new_img)
			new_img = cv2.resize(new_img,(IMG_SIZE,IMG_SIZE))
			if not os.path.exists(save_path):
				os.makedirs(save_path)
			cv2.imwrite(save_path+'/'+img, cv2.cvtColor(new_img, cv2.COLOR_RGB2BGR))

	for dir in testing_dir:
		save_path = os.path.join(BASE_DIR, 'cleaned/Testing/'+ dir)
		path = os.path.join(testing,dir)
		image_dir = os.listdir(path)
		for img in image_dir:
			image = cv2.imread(os.path.join(path,img))
			image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
			new_img = crop_img(image_rgb)
			new_img = normalize_contrast(new_img)
			new_img = cv2.resize(new_img,(IMG_SIZE,IMG_SIZE))
			if not os.path.exists(save_path):
				os.makedirs(save_path)
			cv2.imwrite(save_path+'/'+img, cv2.cvtColor(new_img, cv2.COLOR_RGB2BGR))