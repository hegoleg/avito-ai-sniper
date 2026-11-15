import urllib.request
import cv2
import numpy as np

# Download background image
url = "https://static.geetest.com/pictures/v4_pic/slide_2021_07_14/quiet6/bg/7f007553817e4d1d9a219a132aedbf10.png"
urllib.request.urlretrieve(url, "bg_sample.png")

img = cv2.imread("bg_sample.png")
print("Image shape:", img.shape)

# Convert to grayscale and detect dark shadow / edges
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
blurred = cv2.GaussianBlur(gray, (5, 5), 0)
edges = cv2.Canny(blurred, 100, 200)

cv2.imwrite("bg_edges.png", edges)
print("Saved bg_edges.png")
