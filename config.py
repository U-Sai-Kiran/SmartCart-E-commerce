from dotenv import load_dotenv
import os

load_dotenv()

# SECRET_KEY = os.getenv("SECRET_KEY")
SECRET_KEY = "smartcart-secret-key"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "smartcart_db")

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = "usirikayalasaikiran@gmail.com"
MAIL_PASSWORD = "madw vmfl pvac bbjk"

UPLOAD_FOLDER = "static/uploads/product_images"

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")