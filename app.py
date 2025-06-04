from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory, flash, send_file
from flask_session import Session #flask
import os
import tempfile
import shutil
import pytesseract
from pdf2image import convert_from_path
from google.cloud import texttospeech
import cohere
from transformers import pipeline
from email.mime.text import MIMEText
import smtplib
import threading
import signal
import sys
import random
import re
import glob
import requests
import tiktoken
import json
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import mysql.connector
import itsdangerous
from werkzeug.utils import secure_filename
from sqlalchemy.exc import OperationalError
import base64
import time
import io
from functools import wraps
from io import BytesIO
import uuid
import PyPDF2
from pdfminer.high_level import extract_text as pdfminer_extract_text
import pydub
from pydub.generators import Sine
from sqlalchemy import text
from PIL import Image, ImageDraw
import hashlib
from pydub import AudioSegment
from google.cloud import translate_v2 as translate

# Define availability flags for libraries
GOOGLE_TTS_AVAILABLE = True
COHERE_AVAILABLE = True
PYPDF2_AVAILABLE = True
PDFMINER_AVAILABLE = True
PDF2IMAGE_AVAILABLE = True
PYDUB_AVAILABLE = True
TORCH_AVAILABLE = True

try:
    import torch
except ImportError:
    TORCH_AVAILABLE = False
    print("Warning: PyTorch not installed. Some features may be limited.")

# Setup paths for external tools
POPPLER_PATH = r"C:\\poppler-24.08.0\\Library\\bin"
TESSERACT_CMD = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

try:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
except Exception as e:
    print(f"Warning: Tesseract not properly configured: {e}")

# Initialize QA model only if torch is available
qa_model = None
if TORCH_AVAILABLE:
    try:
        from transformers import pipeline
        qa_model = pipeline("question-answering", model="distilbert-base-cased-distilled-squad", framework="pt")
    except Exception as e:
        print(f"Warning: Could not initialize QA model: {e}")
        qa_model = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SESSION_TYPE'] = 'filesystem'
app.logger.setLevel(logging.INFO)

# Database Configuration
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = ""
MYSQL_DB = "anime_educational"

# Use SQLite as a fallback if MySQL is not available
try:
    # Try to connect to MySQL first
    import pymysql
    # Test connection - will raise an exception if it fails
    test_connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )
    test_connection.close()
    
    # Check if database exists, create if not
    with pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE IF NOT EXISTS anime_educational")
    
    app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}'
    app.logger.info("Using MySQL database")
except Exception as e:
    # Fallback to SQLite
    app.logger.error(f"MySQL connection failed: {e}")
    app.logger.info("Falling back to SQLite database")
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///anime_educational.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = True  # Log all SQL queries for debugging
Session(app)

# setup database
db = SQLAlchemy(app)

# setup login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configure itsdangerous serializer
serializer = itsdangerous.URLSafeTimedSerializer(app.config['SECRET_KEY'])

# user model definitionx
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    recovery_email = db.Column(db.String(120))
    password_hash = db.Column(db.String(128))
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    profile_pic = db.Column(db.String(200), default='default-avatar.png')
    profile_frame = db.Column(db.String(100), default='default')
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    
    # user progress data
    learning_progress = db.Column(db.Text, default='[]')
    goals = db.Column(db.Text, default='[]')
    daily_contributions = db.Column(db.Text, default='{}')
    unlocked_badges = db.Column(db.Text, default='{}')
    unlocked_frames = db.Column(db.Text, default='["default"]') # Frames user has unlocked
    daily_notes = db.Column(db.Text, default='[]') # Daily learning notes
    current_streak = db.Column(db.Integer, default=0)
    best_streak = db.Column(db.Integer, default=0)
    total_contributions = db.Column(db.Integer, default=0)
    quiz_score = db.Column(db.Integer, default=0)
    games_played = db.Column(db.Integer, default=0)
    learning_time = db.Column(db.Integer, default=0)
    
    # chat history relationship
    chat_history = db.relationship('ChatMessage', backref='user', lazy=True, cascade="all, delete-orphan")
    
    # password methods
    def set_password(self, password):
        """Set a hashed password for the user."""
        try:
            # Using werkzeug to securely hash passwords
            self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
            return True
        except Exception as e:
            print(f"Error setting password: {e}")
            return False
        
    def check_password(self, password):
        """Check if the provided password matches the stored hash."""
        if not self.password_hash:
            print(f"Warning: No password hash found for user {self.username}")
            return False
        
        try:
            # Using werkzeug to verify password hash
            return check_password_hash(self.password_hash, password)
        except Exception as e:
            print(f"Error checking password: {e}")
            return False

# chat message model
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=True)  # Make this nullable to handle older schema
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role': self.role,
            'message': self.message,
            'response': self.response if hasattr(self, 'response') else None,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

# Restricted query model for tracking inappropriate user requests
class RestrictedQuery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    query = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.String(100), default='inappropriate content')
    
    def __repr__(self):
        return f"<RestrictedQuery id={self.id} user_id={self.user_id}>"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create database tables if they don't exist
with app.app_context():
    db.create_all()
    
    # Check if daily_notes column exists, and add it if needed
    try:
        # Try to query the column to check if it exists
        db.session.execute(db.select(User.daily_notes).limit(1))
        app.logger.info("daily_notes column exists in User table")
    except Exception as e:
        if 'no such column' in str(e).lower():
            app.logger.info("Adding daily_notes column to User table")
            # SQLite alter table approach
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                db.session.execute(db.text("ALTER TABLE user ADD COLUMN daily_notes TEXT DEFAULT '[]'"))
                db.session.commit()
            # MySQL alter table approach
            else:
                db.session.execute(db.text("ALTER TABLE user ADD COLUMN daily_notes TEXT DEFAULT '[]'"))
                db.session.commit()
            app.logger.info("daily_notes column added successfully")
    
    # Create default profile pics directory if it doesn't exist
    profile_pics_dir = os.path.join('static', 'profile_pics')
    if not os.path.exists(profile_pics_dir):
        os.makedirs(profile_pics_dir)
    # Ensure default avatar exists
    default_avatar = os.path.join('static', 'default-avatar.png')
    if not os.path.exists(default_avatar):
        # Create a simple avatar or copy from another location
        try:
            # If user-avatar.png exists, copy it as default
            user_avatar = os.path.join('static', 'user-avatar.png')
            if os.path.exists(user_avatar):
                import shutil
                shutil.copy(user_avatar, default_avatar)
        except:
            print("Could not create default avatar. Please ensure a default profile image exists.")

# google Cloud credentials explicitly
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r'C:\\Users\\shubh\\Downloads\\anime_educational_chatbot 9th edition\\anime_educational_chatbot 2nd edition\\anime_educational_chatbot\\Keys\\anime-chatbot-auth-47825f559ba6.json'

# Cohere client API
cohere_client = cohere.Client("GCMV08b0j2twLLLNGYQWiZNoukjepvenM7zarQJY")

# TTS client
tts_client = texttospeech.TextToSpeechClient()

# language support for text to speech
LANGUAGE_MAPPING = {
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "ja": "ja-JP",
    "zh": "zh-CN",
    "hi": "hi-IN",
    "ar": "ar-XA",
    "ru": "ru-RU"
}

# Function to translate text between languages using Google Translation API
def translate_text(text, source_language="en", target_language="zh"):
    """Translate text from source language to target language"""
    try:
        app.logger.info(f"Translating text from {source_language} to {target_language}")
        
        # Skip if source and target are the same
        if source_language == target_language:
            return text
            
        # Use Google Translate API
        translate_client = translate.Client()
        
        # The target language code needs to be ISO-639-1 format
        # Our language codes should already match this format
        result = translate_client.translate(
            text, 
            target_language=target_language,
            source_language=source_language
        )
        
        app.logger.info(f"Translation successful")
        return result["translatedText"]
        
    except Exception as e:
        app.logger.error(f"Error translating text: {e}")
        # Return original text if translation fails
        return text

# Define voice configurations for different characters
def get_voice_config(character, language):
    """Get voice configuration for a specific character and language"""
    # Default language code
    language_code = LANGUAGE_MAPPING.get(language, "en-US")
    
    # Character voice configurations
    voice_configs = {
        "Suzie": {
            "en-US": {"voice_name": "en-US-Neural2-F", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "en-US"},
            "es-ES": {"voice_name": "es-ES-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "es-ES"},
            "fr-FR": {"voice_name": "fr-FR-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "fr-FR"},
            "de-DE": {"voice_name": "de-DE-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "de-DE"},
            "ja-JP": {"voice_name": "ja-JP-Neural2-B", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 1.5, "language_code": "ja-JP"},
            "zh-CN": {"voice_name": "cmn-CN-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "cmn-CN"},
            "hi-IN": {"voice_name": "hi-IN-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "hi-IN"},
            "ar-XA": {"voice_name": "ar-XA-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "ar-XA"},
            "ru-RU": {"voice_name": "ru-RU-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "ru-RU"},
            "default": {"voice_name": "en-US-Neural2-F", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.0, "pitch": 2.0, "language_code": "en-US"}
        },
        "Lolita": {
            "en-US": {"voice_name": "en-US-Neural2-C", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "en-US"},
            "es-ES": {"voice_name": "es-ES-Neural2-C", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "es-ES"},
            "fr-FR": {"voice_name": "fr-FR-Neural2-C", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "fr-FR"},
            "de-DE": {"voice_name": "de-DE-Neural2-C", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "de-DE"},
            "ja-JP": {"voice_name": "ja-JP-Neural2-A", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.2, "pitch": 2.5, "language_code": "ja-JP"},
            "zh-CN": {"voice_name": "cmn-CN-Neural2-B", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "cmn-CN"},
            "hi-IN": {"voice_name": "hi-IN-Neural2-B", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "hi-IN"},
            "ar-XA": {"voice_name": "ar-XA-Neural2-B", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "ar-XA"},
            "ru-RU": {"voice_name": "ru-RU-Neural2-B", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "ru-RU"},
            "default": {"voice_name": "en-US-Neural2-C", "gender": texttospeech.SsmlVoiceGender.FEMALE, "speaking_rate": 1.1, "pitch": 3.0, "language_code": "en-US"}
        },
        "Venom": {
            "en-US": {"voice_name": "en-US-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "en-US"},
            "es-ES": {"voice_name": "es-ES-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "es-ES"},
            "fr-FR": {"voice_name": "fr-FR-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "fr-FR"},
            "de-DE": {"voice_name": "de-DE-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "de-DE"},
            "ja-JP": {"voice_name": "ja-JP-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "ja-JP"},
            "zh-CN": {"voice_name": "cmn-CN-Neural2-C", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "cmn-CN"},
            "hi-IN": {"voice_name": "hi-IN-Neural2-C", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "hi-IN"},
            "ar-XA": {"voice_name": "ar-XA-Neural2-C", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "ar-XA"},
            "ru-RU": {"voice_name": "ru-RU-Neural2-C", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "ru-RU"},
            "default": {"voice_name": "en-US-Neural2-D", "gender": texttospeech.SsmlVoiceGender.MALE, "speaking_rate": 0.9, "pitch": -1.0, "language_code": "en-US"}
        }
    }
    
    # Get character config or default to Suzie
    character_config = voice_configs.get(character, voice_configs["Suzie"])
    
    # Get language-specific config or default to character default
    mapped_language = LANGUAGE_MAPPING.get(language, "en-US")
    voice_config = character_config.get(mapped_language, character_config["default"])
    
    # Log what we're doing for debugging
    app.logger.info(f"Using voice config for {character} in {mapped_language}: {voice_config}")
    
    return voice_config

# words that are not allowed in content
RESTRICTED_KEYWORDS = [
    # adult content terms
    "sex", "porn", "xxx", "adult", "nsfw", "naked", "nude", "explicit", 
    "intimate", "erotic", "sexual", "18+", "mature", "fetish", "bdsm",
    "prostitution", "dating", "tinder", "strip", "playboy", "onlyfans",
    "rape", "gangbang", "chudai",
    
    # violence terms
    "violence", "kill", "murder", "assault", "torture", "suicide", 
    "death", "shooting", "terrorist", "bomb", "gun", "weapon", 
    "blood", "gore", "violent", "brutal", "slaughter",
    
    # substance terms
    "drugs", "alcohol", "cigarettes", "smoking", "vaping", "cocaine", 
    "heroin", "marijuana", "weed", "meth", "pills", "ecstasy", 
    "addiction", "inject", "high", "stoned", "drunk",
    
    # gambling terms
    "gambling", "casino", "betting", "lottery", "slots", "poker", 
    "blackjack", "roulette", "jackpot", "wager",
    
    # harmful content terms
    "hate speech", "racism", "discrimination", "nazi", "sexist", "homophobic",
    "cutting", "self-harm", "suicide", "anorexia", "bulimia", "eating disorder",
    "dark web", "hack", "stealing", "theft", "abuse", "harass", "bully"
]

# websites that are not allowed
BLOCKED_DOMAINS = [
    # adult websites
    "porn", "xhamster", "spangbang", "gangbang", "xvideos", "redtube", "xnxx",
    "playboy", "hentai", "brazzers", "pornhub", "youporn", "tube8", "livejasmin",
    "adult", "xxx", "mature", "nsfw", "onlyfans", "patreon-adult",
    
    # harmful websites
    "gambling", "casino", "betting", "drugs", "violence", "explicit",
    "darkweb", "torrent", "warez", "crack", "hack", "pirate", "dating",
    "tinder", "worldstarhiphop"
]

def is_restricted_topic(message):
    # check if message contains restricted words
    message_lower = message.lower()
    for keyword in RESTRICTED_KEYWORDS:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, message_lower):
            return True
    return False

def contains_inappropriate_content(text):
    # check if text is empty
    if not text:
        return False
        
    text_lower = text.lower()
    
    # check for age verification patterns
    age_patterns = [
        r'are you (18|over 18|older than 18)',
        r'confirm your age',
        r'age verification',
        r'adults only',
        r'(not safe|nsfw)',
        r'show me (your|some|naked)'
    ]
    
    for pattern in age_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # check for inappropriate questions
    question_patterns = [
        r'(can|could|will) you (show|tell|give) me [^.]{0,20}(nude|naked|sexy|hot|porn)',
        r'how (to|do you) (have|get) sex',
        r'send me (pic|picture|photo|image)',
        r'what (do|does) [^.]{0,20}(sex|naked|nude|breasts) look like',
        r'tell me about [^.]{0,30}(sex|porn|adult)'
    ]
    
    for pattern in question_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # check for suspicious word combinations
    proximity_patterns = [
        r'(want|show|see|look)[^.]{0,15}(body|naked|nude)',
        r'(pic|picture|photo)[^.]{0,15}(body|girl|boy|woman|man)',
        r'(sex|sexual)[^.]{0,15}(content|material|story)'
    ]
    
    for pattern in proximity_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # check for multiple risk words
    risk_terms = ['body', 'hot', 'sexy', 'girl', 'woman', 'picture', 'photo', 'show me']
    risk_count = sum(1 for term in risk_terms if term in text_lower)
    if risk_count >= 3:
        return True
    
    # check for suspicious urls
    if 'http' in text_lower and any(term in text_lower for term in ['look at', 'check out', 'visit', 'go to']):
        return True
    
    return False

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')  #

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # get form data
        username = request.form.get('username')
        password = request.form.get('password')
        
        # check if fields are filled
        if not username or not password:
            flash('Please provide both username and password', 'error')
            return redirect(url_for('login'))
        
        try:
            # verify user credentials - first try by username
            user = User.query.filter_by(username=username).first()
            
            # If no user found by username, try by email
            if not user:
                user = User.query.filter_by(email=username).first()
            
            if not user:
                app.logger.error(f"No user found with username/email: {username}")
                flash('Invalid username or password', 'error')
                return redirect(url_for('login'))
            
            # Debug info
            app.logger.info(f"User found: {user.username}, checking password")
            
            # Explicitly check password
            pwd_valid = user.check_password(password)
            app.logger.info(f"Password valid: {pwd_valid}")
            
            if pwd_valid:
                # log user in
                login_user(user)
                flash('Login successful!', 'success')
                
                # Store user info in session
                session['registered_email'] = user.email
                session['registered_name'] = user.name
                
                return redirect(url_for('chat_page'))
            else:
                app.logger.error(f"Password check failed for user: {username}")
                flash('Invalid username or password', 'error')
                return redirect(url_for('login'))
            
        except Exception as e:
            app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login. Please try again.', 'error')
            return redirect(url_for('login'))
    
    # show login page
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # get form data
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        name = request.form.get('name')
        
        # validate form data
        if not all([username, email, password, confirm_password, name]):
            flash('Please fill in all fields', 'error')
            return redirect(url_for('register'))
            
        # verify passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
            
        # check password length
        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return redirect(url_for('register'))
            
        # check username availability
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
            
        # check email availability
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        try:
            # create new user
            new_user = User(
                username=username,
                email=email,
                name=name
            )
            new_user.set_password(password)
            
            # save user to database
            db.session.add(new_user)
            db.session.commit()
            
            # save email in session
            session['registered_email'] = email
            session['registered_name'] = name
            
            # Send welcome email
            subject = "Welcome to Anime Educational Chatbot!"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #004754; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0;">Welcome to Anime Educational Chatbot!</h1>
                </div>
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                    <p>Hello {name},</p>
                    <p>Thank you for registering with Anime Educational Chatbot! We're excited to have you join our community.</p>
                    <p>Here are some features you can explore:</p>
                    <ul>
                        <li>Chat with our anime-themed educational bot</li>
                        <li>Take quizzes and track your learning progress</li>
                        <li>Play educational games</li>
                        <li>Explore a variety of anime-related educational content</li>
                    </ul>
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{url_for('chat', _external=True)}" style="background-color: #bebd00; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Start Chatting Now!</a>
                    </div>
                    <p>If you have any questions or feedback, feel free to contact us.</p>
                    <p>Best regards,<br>The Anime Educational Chatbot Team</p>
                </div>
                <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                    <p>© 2023 Anime Educational Chatbot</p>
                </div>
            </body>
            </html>
            """
            send_email_notification(subject, body)
            
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            # handle database errors
            db.session.rollback()
            print(f"Registration error: {e}")
            flash('An error occurred during registration', 'error')
            return redirect(url_for('register'))
            
    # show registration page
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/progress_tracker')
@login_required
def progress_tracker():
    return render_template('progress_tracker.html', user=current_user)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    try:
        # Load available frames
        available_frames = [
            {"id": "default", "name": "Default", "description": "Basic frame"},
            {"id": "gold", "name": "Gold Frame", "description": "Awarded for achieving 100 points"},
            {"id": "silver", "name": "Silver Frame", "description": "Awarded for 10 consecutive days of learning"},
            {"id": "bronze", "name": "Bronze Frame", "description": "Awarded for completing 5 quizzes"},
            {"id": "platinum", "name": "Platinum Frame", "description": "Awarded for all achievements"}
        ]
        
        # Ensure all required columns exist before proceeding
        ensure_db_structure()
        
        # Check if the default avatar exists
        default_avatar_path = os.path.join('static', 'default-avatar.png')
        if not os.path.exists(default_avatar_path):
            app.logger.warning("Default avatar not found, will use a placeholder")
            # Set default avatar to an empty string if the file doesn't exist
            if current_user.profile_pic == 'default-avatar.png':
                current_user.profile_pic = ''
                
        # Ensure profile_pic is properly formatted
        if current_user.profile_pic and not current_user.profile_pic.startswith(('http://', 'https://', 'profile_pics/')):
            current_user.profile_pic = f'profile_pics/{current_user.profile_pic}'
            db.session.commit()
        
        # Get user's unlocked frames
        try:
            unlocked_frames = json.loads(current_user.unlocked_frames or '["default"]')
        except (json.JSONDecodeError, TypeError):
            app.logger.warning(f"Invalid unlocked_frames data for user {current_user.id}. Resetting to default.")
            unlocked_frames = ["default"]
            current_user.unlocked_frames = json.dumps(unlocked_frames)
            db.session.commit()
        
        if request.method == 'POST':
            # get form data
            name = request.form.get('name')
            age = request.form.get('age')
            recovery_email = request.form.get('recovery_email')
            selected_frame = request.form.get('profile_frame')
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # update name if provided
            if name:
                current_user.name = name
                session['registered_name'] = name
            
            # update age if provided
            if age:
                try:
                    current_user.age = int(age)
                except ValueError:
                    pass
            
            # update recovery email if provided
            if recovery_email:
                # Validate email format
                if re.match(r"[^@]+@[^@]+\.[^@]+", recovery_email):
                    current_user.recovery_email = recovery_email
                else:
                    return render_template('profile.html', 
                                           user=current_user,
                                           frames=available_frames,
                                           unlocked_frames=unlocked_frames,
                                           error="Invalid recovery email format")
            
            # update profile frame if provided and unlocked
            if selected_frame and selected_frame in unlocked_frames:
                current_user.profile_frame = selected_frame
            
            # handle profile picture
            if 'profile_pic' in request.files:
                profile_pic = request.files['profile_pic']
                if profile_pic and profile_pic.filename:
                    # Check file extension
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                    file_ext = profile_pic.filename.rsplit('.', 1)[1].lower() if '.' in profile_pic.filename else ''
                    
                    if file_ext not in allowed_extensions:
                        return render_template('profile.html', 
                                              user=current_user, 
                                              frames=available_frames,
                                              unlocked_frames=unlocked_frames,
                                              error="Only image files (png, jpg, jpeg, gif) are allowed")
                    
                    # Create safe filename with user ID to ensure uniqueness
                    filename = f"user_{current_user.id}_{int(datetime.utcnow().timestamp())}.{file_ext}"
                    
                    # Save file
                    upload_path = os.path.join('static', 'profile_pics')
                    os.makedirs(upload_path, exist_ok=True)
                    file_path = os.path.join(upload_path, filename)
                    profile_pic.save(file_path)
                    
                    # Delete old profile pic if it exists and isn't the default
                    if current_user.profile_pic and current_user.profile_pic != 'default-avatar.png':
                        old_pic_path = os.path.join('static', current_user.profile_pic)
                        if os.path.exists(old_pic_path):
                            try:
                                os.remove(old_pic_path)
                                app.logger.info(f"Removed old profile picture: {old_pic_path}")
                            except Exception as e:
                                app.logger.error(f"Error removing old profile picture: {e}")
                    
                    # Update user profile pic in database
                    current_user.profile_pic = f"profile_pics/{filename}"
            
            # handle password change
            if current_password and new_password and confirm_password:
                if not current_user.check_password(current_password):
                    return render_template('profile.html', 
                                          user=current_user, 
                                          frames=available_frames,
                                          unlocked_frames=unlocked_frames,
                                          error="Current password is incorrect")
                
                if new_password != confirm_password:
                    return render_template('profile.html', 
                                          user=current_user, 
                                          frames=available_frames,
                                          unlocked_frames=unlocked_frames,
                                          error="New passwords do not match")
                
                # Validate password complexity
                if len(new_password) < 8:
                    return render_template('profile.html', 
                                          user=current_user, 
                                          frames=available_frames,
                                          unlocked_frames=unlocked_frames,
                                          error="Password must be at least 8 characters long")
                
                current_user.set_password(new_password)
            
            # save changes
            db.session.commit()
            
            # Success message
            return render_template('profile.html', 
                                  user=current_user, 
                                  frames=available_frames,
                                  unlocked_frames=unlocked_frames,
                                  success="Profile updated successfully")
        
        # show profile page
        return render_template('profile.html', 
                              user=current_user,
                              frames=available_frames,
                              unlocked_frames=unlocked_frames)
    except Exception as e:
        app.logger.error(f"Profile page error: {str(e)}")
        return render_template('error.html', error=f"An error occurred: {str(e)}")

@app.route('/chat_page')
@login_required
def chat_page():
    # Ensure educational images directory exists
    create_default_educational_images()
    return render_template('chat_page.html', registered_name=session.get('registered_name', 'User'), current_user=current_user)

def create_default_educational_images():
    """Create default educational images if they don't exist"""
    try:
        # Ensure directories exist
        edu_img_dir = os.path.join('static', 'images', 'educational')
        os.makedirs(edu_img_dir, exist_ok=True)
        
        # Define topic colors for simple colored images
        topic_colors = {
            'math.jpg': (50, 100, 230),     # Blue
            'science.jpg': (40, 180, 70),   # Green
            'history.jpg': (200, 120, 40),  # Brown
            'space.jpg': (70, 40, 120),     # Dark purple
            'computer.jpg': (30, 150, 180), # Teal
            'art.jpg': (180, 50, 140)       # Pink
        }
        
        # Create default images using PIL
        for filename, color in topic_colors.items():
            target_path = os.path.join(edu_img_dir, filename)
            if not os.path.exists(target_path):
                try:
                    # Create a simple colored image with text
                    img = Image.new('RGB', (400, 400), color=color)
                    draw = ImageDraw.Draw(img)
                    
                    # Draw a border
                    border_width = 10
                    for i in range(border_width):
                        draw.rectangle(
                            [(i, i), (399-i, 399-i)],
                            outline=(255, 255, 255)
                        )
                    
                    # Add text (topic name)
                    topic_name = filename.split('.')[0].upper()
                    
                    # Draw outline of text for better visibility
                    for offset_x, offset_y in [(-2,-2), (-2,2), (2,-2), (2,2)]:
                        draw.text(
                            (200 + offset_x, 200 + offset_y),
                            topic_name,
                            fill=(0, 0, 0),
                            anchor="mm"
                        )
                    
                    # Draw main text
                    draw.text(
                        (200, 200),
                        topic_name,
                        fill=(255, 255, 255),
                        anchor="mm"
                    )
                    
                    # Save the image
                    img.save(target_path)
                    app.logger.info(f"Created default image: {target_path}")
                except Exception as create_error:
                    app.logger.error(f"Error creating image {target_path}: {create_error}")
                    
                    # Fall back to copying default avatar if PIL drawing fails
                    default_avatar = os.path.join('static', 'default-avatar.png')
                    if os.path.exists(default_avatar):
                        try:
                            shutil.copy(default_avatar, target_path)
                            app.logger.info(f"Copied default avatar to {target_path}")
                        except Exception as copy_error:
                            app.logger.error(f"Error copying default avatar: {copy_error}")
    except Exception as e:
        app.logger.error(f"Error creating default educational images: {e}")

@app.route('/quiz_page')
@login_required
def quiz_page():
    return render_template('quiz_page.html')

@app.route('/get_random_questions', methods=['GET'])
@login_required
def get_random_questions():
    import random
    # Math
    math_a, math_b = random.randint(1, 20), random.randint(1, 20)
    math_answer = math_a + math_b
    math_options = [math_answer, math_answer + random.randint(1, 5), math_answer - random.randint(1, 3), math_answer + random.randint(6, 10)]
    math_options = list(dict.fromkeys([str(opt) for opt in math_options]))
    while len(math_options) < 4:
        extra = str(random.randint(1, 40))
        if extra not in math_options:
            math_options.append(extra)
    math_options = math_options[:4]
    random.shuffle(math_options)

    # Science
    science_q = "Which planet is known as the Red Planet?"
    science_options = ["Earth", "Mars", "Jupiter", "Venus"]
    science_options = [str(opt) for opt in science_options][:4]
    random.shuffle(science_options)

    # GK
    gk_q = "What is the largest ocean on Earth?"
    gk_options = ["Atlantic Ocean", "Indian Ocean", "Arctic Ocean", "Pacific Ocean"]
    gk_options = [str(opt) for opt in gk_options][:4]
    random.shuffle(gk_options)

    response = {
        "math": {
            "question": f"What is {math_a} + {math_b}?",
            "answer": str(math_answer),
            "options": math_options
        },
        "science": {
            "question": science_q,
            "options": science_options,
            "answer": "Mars"
        },
        "gk": {
            "question": gk_q,
            "options": gk_options,
            "answer": "Pacific Ocean"
        },
        "questions": [
            {
                "question": f"What is {math_a} + {math_b}?",
                "options": math_options,
                "correct_answer": str(math_answer)
            },
            {
                "question": science_q,
                "options": science_options,
                "correct_answer": "Mars"
            },
            {
                "question": gk_q,
                "options": gk_options,
                "correct_answer": "Pacific Ocean"
            }
        ]
    }
    return jsonify(response)

@app.route('/games_page')
def games_page():
    return render_template("games_page.html")

# Function to generate speech for responses (Updated & Integrated)
def generate_speech(text, character="Suzie", language="en"):
    """Generate speech audio from text with improved error handling and fallbacks"""
    try:
        app.logger.info(f"Generating speech for character '{character}' in language '{language}'")
        
        # Clean text for TTS
        clean_text = re.sub(r'[^\w\s.,?!]', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Limit text length to avoid exceeding API limits
        if len(clean_text) > 5000:
            clean_text = clean_text[:5000] + "..."
        
        # Create Cloud TTS request
        client = texttospeech.TextToSpeechClient()
        
        # Set input text
        synthesis_input = texttospeech.SynthesisInput(text=clean_text)
        
        # Get voice configuration based on character and language
        voice_config = get_voice_config(character, language)
        
        # Log voice config for debugging
        app.logger.info(f"Voice config: {voice_config}")
        
        # Get language code from voice_config or use default mapping
        language_code = LANGUAGE_MAPPING.get(language, "en-US")
        if 'language_code' in voice_config:
            language_code = voice_config['language_code']
        
        # Create voice selection parameters
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code,
            name=voice_config['voice_name'],
            ssml_gender=voice_config['gender']
        )
        
        # Set audio configuration
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=voice_config.get('speaking_rate', 1.0),
            pitch=voice_config.get('pitch', 0.0)
        )
        
        # Perform text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        # Ensure audio directory exists
        os.makedirs('static/audio', exist_ok=True)
        
        # Create a unique filename based on hash of text and timestamp
        filename = f"{character}_{hashlib.md5(clean_text.encode()).hexdigest()[:10]}_{int(time.time())}.mp3"
        file_path = os.path.join('static/audio', filename)
        
        # Write the response content to file
        with open(file_path, 'wb') as out:
            out.write(response.audio_content)
            
        app.logger.info(f"Audio content written to file: {file_path}")
        
        # Return the path relative to static for the front-end
        return f"/static/audio/{filename}"
    
    except Exception as e:
        app.logger.error(f"Error generating speech: {e}")
        # Try fallback TTS
        fallback_path = use_fallback_tts(text, character, language)
        if fallback_path:
            # Return the path properly for frontend
            if not fallback_path.startswith('/'):
                return f"/{fallback_path.replace('\\', '/').replace('static/', 'static/')}"
            return fallback_path
        
        # If all else fails, return a simple tone
        return generate_simple_audio_tone_file()

def generate_simple_audio_tone_file():
    """Generate a simple audio tone as a fallback and return the file path"""
    try:
        if not PYDUB_AVAILABLE:
            app.logger.warning("Pydub not available for fallback tone generation")
            return None
            
        # Ensure audio directory exists
        os.makedirs('static/audio', exist_ok=True)
        
        # Create a simple sine wave tone
        sample_rate = 44100
        duration_ms = 1000
        frequency = 440  # A4 note
        
        # Generate the tone
        sine_wave = AudioSegment.silent(duration=duration_ms)
        for i in range(0, duration_ms, 100):
            sine_chunk = sine_wave.overlay(
                AudioSegment.sine(frequency, duration=100, volume=-10),
                position=i
            )
            sine_wave = sine_wave.overlay(sine_chunk)
        
        # Generate a unique filename
        tone_filename = f"tone_{int(time.time())}.mp3"
        tone_path = os.path.join('static/audio', tone_filename)
        
        # Export the audio file
        sine_wave.export(tone_path, format="mp3")
        app.logger.info(f"Generated fallback tone at {tone_path}")
        
        # Return the path relative to static for the front-end
        return f"/static/audio/{tone_filename}"
    
    except Exception as e:
        app.logger.error(f"Error generating audio tone: {e}")
        return None

def use_fallback_tts(text, character, language):
    """Fallback method for text-to-speech when Google Cloud TTS fails"""
    app.logger.info("Using fallback TTS method")
    
    try:
        # Create a simple TTS using gTTS (Google Text-to-Speech) library
        try:
            from gtts import gTTS
            
            # Map language codes for gTTS
            gtts_language = language[:2]  # gTTS uses 2-char language codes
            
            # Create audio file
            audio_dir = os.path.join('static', 'audio')
            os.makedirs(audio_dir, exist_ok=True)
            
            # Generate unique filename
            timestamp = int(datetime.utcnow().timestamp())
            content_hash = hash(text + character + language) % 10000
            filename = f"fallback_speech_{timestamp}_{content_hash}.mp3"
            output_file = os.path.join(audio_dir, filename)
            
            # Generate and save the audio
            tts = gTTS(text=text, lang=gtts_language, slow=False)
            tts.save(output_file)
            
            app.logger.info(f"Fallback speech generated successfully: {output_file}")
            # Return proper web path format
            return f"/static/audio/{filename}"
            
        except ImportError as ie:
            app.logger.warning(f"gTTS not installed, cannot use as fallback: {ie}")
            
        # If gTTS fails or isn't installed, try one more fallback method
        # This is a mock fallback that simply creates a silent audio file
        try:
            from pydub import AudioSegment
            from pydub.generators import Sine
            
            # Create a brief beep sound to indicate text
            beep = Sine(440).to_audio_segment(duration=500)
            silent = AudioSegment.silent(duration=1000)
            audio = silent + beep + silent
            
            # Save the audio
            audio_dir = os.path.join('static', 'audio')
            os.makedirs(audio_dir, exist_ok=True)
            
            timestamp = int(datetime.utcnow().timestamp())
            filename = f"silent_fallback_{timestamp}.mp3"
            output_file = os.path.join(audio_dir, filename)
            
            audio.export(output_file, format="mp3")
            app.logger.info(f"Silent fallback audio created: {output_file}")
            # Return proper web path format
            return f"/static/audio/{filename}"
            
        except ImportError as ie:
            app.logger.warning(f"pydub not installed, cannot create silent audio: {ie}")
            
    except Exception as fallback_error:
        app.logger.error(f"Fallback TTS error: {str(fallback_error)}")
    
    return None

def send_email_notification(subject, body):
    # email settings
    sender_email = "shubhrakeshnahar@gmail.com"
    sender_password = "rbbh mvre zhmn ctgd"
    
    # get recipient email
    recipient_email = session.get("registered_email")
    if not recipient_email and 'email' in request.form:
        recipient_email = request.form.get("email")
    
    # prepare email
    msg = MIMEText(body, 'html')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email
    
    try:
        # send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print(f"Email sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        # try backup method
        def send_email_async():
            try:
                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.sendmail(sender_email, recipient_email, msg.as_string())
            except Exception as inner_e:
                print(f"backup email failed: {inner_e}")
        
        # send email in background
        email_thread = threading.Thread(target=send_email_async)
        email_thread.daemon = True
        email_thread.start()

# Function to count tokens
def count_tokens(text):
    # count tokens in text
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

# Function to get chatbot response
def get_response(user_message, chat_history):
    try:
        # Handle current time and year queries
        if "current time" in user_message.lower() or "what time is it" in user_message.lower():
            current_time = datetime.now().strftime("%I:%M %p")
            return f"The current time is {current_time}."
            
        if "current year" in user_message.lower() or "what year is it" in user_message.lower():
            current_year = datetime.now().year
            return f"The current year is {current_year}."
            
        if is_restricted_topic(user_message) or contains_inappropriate_content(user_message):
            subject = "Restricted Topic Accessed"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #e74c3c; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0;">⚠️ Restricted Content Alert ⚠️</h1>
                </div>
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                    <p>Dear {session.get('registered_name', 'User')},</p>
                    
                    <div style="background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 5px solid #e74c3c;">
                        <h2 style="margin: 0; font-size: 18px;">Content Access Notice</h2>
                        <p style="margin: 10px 0 0 0;">You have accessed a restricted topic that is not appropriate for an educational environment.</p>
                    </div>
                    
                    <div style="background-color: #f2f2f2; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; font-weight: bold;">Query Reference:</p>
                        <p style="margin: 10px 0 0 0; font-style: italic;">"{user_message}"</p>
                    </div>
                    
                    <p>Your session has been ended to maintain our educational focus.</p>
                    <p>Please refrain from accessing such topics in the future and focus on educational content.</p>
                    
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{request.host_url}" style="background-color: #e74c3c; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Return to Educational Content</a>
                    </div>
                    
                    <p>Best regards,<br>Anime Educational Chatbot Team</p>
                </div>
                <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                    <p>© 2023 Anime Educational Chatbot</p>
                </div>
            </body>
            </html>
            """
            send_email_notification(subject, body)
            return "This topic is restricted. Your session has been ended and an alert has been sent to your registered email."

        # Handle math queries
        if re.match(r'^\s*\d+(\s*[\+\-\*/]\s*\d+)+\s*$', user_message):
            return str(eval(user_message))

        # Trim chat history if too long
        max_tokens = 2000
        chat_history_tokens = sum(count_tokens(item["message"]) for item in chat_history)

        while chat_history and chat_history_tokens + count_tokens(user_message) > max_tokens:
            removed = chat_history.pop(0)
            chat_history_tokens -= count_tokens(removed["message"])

        # Call Cohere API directly instead of using the generate function
        try:
            # Try using the chat endpoint first
            response = cohere_client.chat(
                message=user_message,
                model="command",
                temperature=0.7,
                prompt_truncation="AUTO"
            )
            response_text = response.text
        except Exception as chat_error:
            app.logger.warning(f"Error using chat endpoint: {chat_error}, falling back to generate")
            # Fallback to generate endpoint
            response = cohere_client.generate(
                model="command",
                prompt=f"User: {user_message}\nAnime educational chatbot:",
                max_tokens=200,
                temperature=0.7
            )
            response_text = response.generations[0].text.strip()

        # Skip summarization which might be causing errors
        # Just clean up the response directly
        short_response = response_text.replace("\n\n", "\n").strip()
            
        if not short_response.endswith("."):
            short_response += "."

        return short_response

    except Exception as e:
        print(f"Error in chatbot response: {e}")
        return "I'm not sure about that. Can you ask differently?"
    
# Fetch images & links from Google API
def fetch_google_results(query, search_type="web"):
    search_url = f"https://www.googleapis.com/customsearch/v1?q={query}&key=AIzaSyCULGMkB4dgunsnwYJmpraHFIx9kEPmqdU&cx=d4d9482d288924e1a"
    if search_type == "image":
        search_url += "&searchType=image"

    try:
        app.logger.info(f"Fetching Google results for query: '{query}' (type: {search_type})")
        response = requests.get(search_url, timeout=10)
        
        # Log HTTP status code
        app.logger.info(f"Google API response status: {response.status_code}")
        
        # Handle non-200 responses explicitly
        if response.status_code != 200:
            app.logger.error(f"Google API returned status code {response.status_code}")
            app.logger.error(f"Response text: {response.text[:200]}...")
            return {"error": f"API error: {response.status_code}", "items": []}
            
        data = response.json()
        
        if 'items' in data:
            if search_type == "image":
                app.logger.info(f"Received {len(data['items'])} image results")
                # Log the first image URL for debugging
                if len(data['items']) > 0:
                    app.logger.info(f"First image URL: {data['items'][0].get('link', 'No link available')}")
            else:
                app.logger.info(f"Received {len(data['items'])} web search results")
        else:
            error_msg = data.get('error', {}).get('message', 'No error message')
            app.logger.warning(f"No items found in Google API response: {error_msg}")
            
            # If there's an error in the response, log it
            if 'error' in data:
                app.logger.error(f"API error details: {data['error']}")
                
            # Return a minimal response with the error
            return {"error": error_msg, "items": []}
            
        return data
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Google search error: {e}")
        return {"error": f"Request failed: {str(e)}", "items": []}
    except Exception as e:
        app.logger.error(f"Unexpected error in fetch_google_results: {str(e)}")
        return {"error": f"Unexpected error: {str(e)}", "items": []}

def is_safe_link(link):
    """Enhanced check if the link is safe for children."""
    if not link:
        return False
    
    # Convert to lowercase for matching
    link_lower = link.lower()
    
    # Block any domain containing restricted keywords
    if any(blocked in link_lower for blocked in BLOCKED_DOMAINS):
        print(f"⚠️ Blocked domain detected in link: {link}")
        return False
    
    # Specifically allow only educational and child-friendly domains
    SAFE_DOMAINS = [
        "wikipedia.org", "britannica.com", "nationalgeographic.com", 
        "nasa.gov", "khanacademy.org", "brainpop.com", "discoveryeducation.com",
        "pbs.org", "scholastic.com", "howstuffworks.com", "sciencekids.co.nz",
        "coolmath.com", "ducksters.com", "wonderopolis.org", "time4learning.com",
        "funkidslive.com", "smithsonianmag.com", "abcya.com", "starfall.com",
        "kids.nationalgeographic.com", "factmonster.com", "bbc.co.uk/bitesize",
        "education.com", "sheppardsoftware.com", "funbrain.com", 
        "historyforkids.net", "mathsisfun.com", "sciencebuddies.org"
    ]
    
    # Check if the link is from a known safe educational domain
    is_known_safe = any(safe_domain in link_lower for safe_domain in SAFE_DOMAINS)
    
    # Extra checks for non-whitelisted domains
    if not is_known_safe:
        # Block links to downloadable content
        if any(ext in link_lower for ext in [".exe", ".zip", ".rar", ".apk", ".dmg", ".pdf"]):
            print(f"⚠️ Blocked download link: {link}")
            return False
            
        # Block links with suspicious terms in URL
        suspicious_terms = ["download", "game", "free", "play", "video", "chat", "login", "sign-up", "account"]
        if any(term in link_lower for term in suspicious_terms):
            print(f"⚠️ Suspicious term in URL: {link}")
            return False
    
    return True   

def filter_safe_links(links):
    """Filter out unsafe links and prioritize educational websites for children."""
    safe_links = [link for link in links if is_safe_link(link)]
    print(f"Safe links after filtering: {safe_links}") 
    
    # Prioritize educational websites
    wikipedia_links = [link for link in safe_links if "wikipedia.org" in link]
    educational_links = [link for link in safe_links if any(edu in link for edu in [
        "nationalgeographic", "nasa.gov", "khanacademy", "britannica", 
        "scholastic", "education", "pbs.org", "science", "math", "history"
    ])]
    other_links = [link for link in safe_links if link not in wikipedia_links and link not in educational_links]
    
    # Return prioritized links (max 3 total)
    final_links = (wikipedia_links[:1] + educational_links[:1] + other_links[:1])[:3]
    print(f"Final links after prioritization: {final_links}")
    return final_links

def filter_safe_images(images):
    """Filter out potentially unsafe images for children and download them locally."""
    # Start with basic domain filtering
    domain_filtered_images = [image for image in images if is_safe_link(image)]
    
    # Apply additional image-specific filtering, but with less aggressive filtering
    safe_images = []
    for image in domain_filtered_images:
        image_lower = image.lower()
        
        # Skip images from general photo sharing sites unless from educational sections
        # For this case, make an exception for nature-related queries
        photo_sites = ["flickr.com", "imgur.com", "shutterstock", "gettyimages", "unsplash", "pexels"]
        if any(site in image_lower for site in photo_sites) and not any(edu in image_lower for edu in ["science", "education", "learn", "school", "study", "nature", "flower", "plant", "biology"]):
            continue
            
        # Skip images with suspicious terms in the URL, but allow terms related to plants and nature
        suspicious_terms = ["profile", "user", "avatar"]  # Removed "person", "people", "girl", "boy", "woman", "man"
        if any(term in image_lower for term in suspicious_terms):
            continue
            
        safe_images.append(image)
    
    # If we still have no images after filtering, use the original list with minimal filtering
    if not safe_images and domain_filtered_images:
        app.logger.warning("No images left after strict filtering, using less strict filtering")
        safe_images = domain_filtered_images
    
    # Limit to at most 3 images
    selected_images = safe_images[:3]
    
    # Download and save the images locally
    local_image_paths = []
    for image_url in selected_images:
        local_path = download_and_save_image(image_url)
        if local_path:
            local_image_paths.append(local_path)
    
    # If we couldn't download any images, use default
    if not local_image_paths:
        return ["static/default-avatar.png"]
        
    app.logger.info(f"Safe images after filtering and downloading: {local_image_paths}")
    return local_image_paths

def download_and_save_image(image_url):
    """Download an image from URL and save it locally."""
    try:
        app.logger.info(f"Downloading image from: {image_url}")
        
        # Create a unique local filename
        image_filename = f"image_{int(time.time())}_{random.randint(1000, 9999)}.jpg"
        local_dir = os.path.join('static', 'downloaded_images')
        local_path = os.path.join(local_dir, image_filename)
        
        # Ensure the download directory exists with proper permissions
        os.makedirs(local_dir, exist_ok=True)
        
        # Download the image
        response = requests.get(image_url, stream=True, timeout=5)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Check content type to verify it's actually an image
        content_type = response.headers.get('Content-Type', '')
        if not content_type.startswith('image/'):
            app.logger.warning(f"URL does not point to an image: {content_type}")
            return None
            
        # Save the image
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        app.logger.info(f"Image successfully saved to {local_path}")
        
        # Return URL path that can be used by the frontend
        return f"/static/downloaded_images/{image_filename}"
        
    except Exception as e:
        app.logger.error(f"Error downloading image {image_url}: {e}")
        return None

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    if not file:
        return jsonify({"error": "No file received"}), 400

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    file.save(file_path)

    return jsonify({"message": "File uploaded successfully", "file_path": file_path})

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    data = request.json
    file_path = data.get('file_path')

    if not file_path or not os.path.exists(file_path):
        return jsonify({
            "error": "File not found.",
            "status": "error",
            "extracted_text": ""
        }), 400

    extracted_text = extract_text_from_pdf(file_path)
    app.logger.info(f"[PDF DEBUG] Extracted text (first 500 chars): {extracted_text[:500]}")

    if not extracted_text or len(extracted_text.strip()) < 20:
        return jsonify({
            "error": "No readable text found in the PDF. It may be image-based, empty, or protected. Please upload a text-based PDF.",
            "status": "error",
            "extracted_text": extracted_text
        }), 400

    mcqs = generate_mcqs_from_text(extracted_text)
    app.logger.info(f"[PDF DEBUG] Generated MCQs: {mcqs}")

    # Always return at least one MCQ if possible
    if "mcqs" in mcqs and len(mcqs["mcqs"]) >= 1:
        return jsonify({
            "mcqs": mcqs["mcqs"][:3],
            "status": "success",
            "extracted_text": extracted_text
        })
    else:
        # Fallback: Always provide a generic MCQ
        fallback_mcq = {
            "question": "What is the main topic of this document?",
            "options": ["Education", "Science", "Technology", "History"],
            "correct_answer": "Education"
        }
        return jsonify({
            "mcqs": [fallback_mcq],
            "status": "fallback",
            "extracted_text": extracted_text,
            "error": mcqs.get("error", "No MCQs generated. Fallback used.")
        })

def extract_text_from_pdf(file_path):
    """Extract text from a PDF file with improved error handling and fallbacks"""
    app.logger.info(f"Extracting text from: {file_path}")
    
    text = ""
    
    # First attempt: Try using PyPDF2
    if PYPDF2_AVAILABLE:
        try:
            app.logger.info("Attempting PDF extraction with PyPDF2")
            with open(file_path, 'rb') as file:
                # Updated for PyPDF2 3.0+ API
                pdf_reader = PyPDF2.PdfReader(file)
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text += page.extract_text()
            
            if text.strip():
                app.logger.info(f"Successfully extracted {len(text)} characters from PDF using PyPDF2")
                return text
            else:
                app.logger.info("PyPDF2 extraction returned no text, trying alternative method")
        except Exception as e:
            app.logger.warning(f"PyPDF2 extraction failed: {str(e)}")
    
    # Second attempt: Try using pdfminer
    if PDFMINER_AVAILABLE:
        try:
            app.logger.info("Attempting PDF extraction with pdfminer")
            text = pdfminer_extract_text(file_path)
            
            if text.strip():
                app.logger.info(f"Successfully extracted {len(text)} characters from PDF using pdfminer")
                return text
            else:
                app.logger.info("pdfminer extraction returned no text, trying OCR method")
        except Exception as e:
            app.logger.warning(f"pdfminer extraction failed: {str(e)}")
    
    # Third attempt: Try OCR with pdf2image and pytesseract
    if PDF2IMAGE_AVAILABLE:
        try:
            app.logger.info("Attempting PDF extraction with OCR (pdf2image and pytesseract)")
            # Check if the poppler path is valid
            if os.path.exists(POPPLER_PATH):
                images = convert_from_path(file_path, poppler_path=POPPLER_PATH)
            else:
                # Try without specifying poppler path
                app.logger.info("Poppler path not found, trying without it")
                images = convert_from_path(file_path)
                
            for img in images:
                text += pytesseract.image_to_string(img)
            
            if text.strip():
                app.logger.info(f"Successfully extracted {len(text)} characters from PDF using OCR")
                return text
            else:
                app.logger.warning("OCR extraction returned no text")
        except Exception as e:
            app.logger.error(f"OCR extraction failed: {str(e)}")
    
    # Fallback message if all methods fail
    if not text.strip():
        app.logger.error("All PDF extraction methods failed")
        text = "Unable to extract text from the PDF. The file might be encrypted, scanned without OCR, or in an unsupported format."
    
    return text

def generate_mcqs_from_text(text):
    """Generate MCQs using Cohere Chat API with improved error handling and token management."""
    try:
        # Trim input text to avoid exceeding the token limit
        max_input_tokens = 3000  # Keeping buffer within Cohere's 4096 token limit
        text_tokens = text.split()[:max_input_tokens]  # Split text into words and truncate
        trimmed_text = " ".join(text_tokens)

        # Create a prompt for generating MCQs
        prompt = f"""
        Generate 3 multiple-choice questions (MCQs) from the following text. 
        For each question, provide 4 options and indicate the correct answer.
        Keep the answers simple and clear.

        Text:
        {trimmed_text}

        Format each question EXACTLY like this:
        Question: What is the capital of France?
        Options:
        A) London
        B) Paris
        C) Rome
        D) Berlin
        Correct Answer: B

        Make sure each question is on a new line and follows this format precisely.
        """

        app.logger.info("Calling Cohere API for MCQ generation")
        
        # Use the Cohere Chat API to generate MCQs with improved parameters
        response = cohere_client.generate(
            model="command-light",  # Use the lighter model for better reliability
            prompt=prompt,
            temperature=0.4,  # Lower temperature for more predictable output
            max_tokens=800,  # Increased for more complete responses
            presence_penalty=0.2,  # Discourage repetition
            frequency_penalty=0.2,  # Discourage repetition
            stop_sequences=["\n\n\n"]  # Stop at three newlines to maintain format
        )

        # Log the raw response for debugging
        if not hasattr(response, "generations") or not response.generations:
            app.logger.error("Cohere API returned an empty response.")
            return fallback_mcq_generation(trimmed_text)
        
        response_text = response.generations[0].text.strip()
        app.logger.info(f"Raw Cohere Response (first 100 chars): {response_text[:100]}...")

        if not response_text:
            app.logger.error("Cohere API returned an empty response text.")
            return fallback_mcq_generation(trimmed_text)

        mcqs = []
        # Split by "Question:" to separate individual questions
        question_blocks = response_text.split("Question:")
        
        # Process each question block
        for block in question_blocks:
            if not block.strip():
                continue
                
            try:
                # Normalize the format by adding back "Question:" prefix if needed
                block = "Question:" + block if not block.startswith("Question:") else block
                lines = [line.strip() for line in block.split("\n") if line.strip()]
                
                if len(lines) < 6:  # Minimum lines needed for a complete MCQ
                    continue
                    
                question_text = lines[0].replace("Question:", "").strip()
                options = []
                correct_answer = None
                
                # Extract options
                for i in range(1, len(lines)):
                    line = lines[i]
                    if line.startswith("Options:"):
                        continue
                    elif line.startswith("A)") or line.startswith("A."):
                        options.append(line.replace("A)", "").replace("A.", "").strip())
                    elif line.startswith("B)") or line.startswith("B."):
                        options.append(line.replace("B)", "").replace("B.", "").strip())
                    elif line.startswith("C)") or line.startswith("C."):
                        options.append(line.replace("C)", "").replace("C.", "").strip())
                    elif line.startswith("D)") or line.startswith("D."):
                        options.append(line.replace("D)", "").replace("D.", "").strip())
                    elif line.startswith("Correct Answer:") or line.startswith("Correct answer:"):
                        answer = line.replace("Correct Answer:", "").replace("Correct answer:", "").strip()
                        # Map the letter answer to the option index (0-based)
                        answer_mapping = {"A": 0, "B": 1, "C": 2, "D": 3}
                        # Extract the letter if the answer is like "A" or "A)" or "Option A"
                        for key in answer_mapping:
                            if answer.startswith(key) or answer == key:
                                correct_answer = answer_mapping.get(key, 0)
                                break
                        # Default to first option if can't parse
                        if correct_answer is None:
                            correct_answer = 0
                
                # Only add if we have a complete question with options
                if question_text and len(options) >= 3 and correct_answer is not None:
                    mcq = {
                        "question": question_text,
                        "options": options,
                        "correct_answer": options[correct_answer] if correct_answer < len(options) else options[0]
                    }
                    mcqs.append(mcq)
            except Exception as parsing_error:
                app.logger.error(f"Error parsing MCQ: {parsing_error}")
                continue

        # Checking if MCQs were successfully extracted
        if not mcqs:
            app.logger.warning("No valid MCQs extracted. Using fallback method.")
            return fallback_mcq_generation(trimmed_text)

        return {"mcqs": mcqs}

    except Exception as e:
        app.logger.error(f"Cohere API error: {e}")
        return fallback_mcq_generation(trimmed_text)

def fallback_mcq_generation(text):
    """Fallback method to generate basic MCQs when the API fails"""
    app.logger.info("Using fallback MCQ generation")
    
    # Extract key sentences from the text
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if len(s.strip()) > 20]
    
    if not sentences:
        return {"error": "Could not generate questions from the provided text."}
    
    # Use at most 3 sentences for questions
    selected_sentences = sentences[:3] if len(sentences) >= 3 else sentences
    
    mcqs = []
    
    # Generate a very simple fill-in-the-blank MCQ for each sentence
    for sentence in selected_sentences:
        words = sentence.split()
        if len(words) < 5:
            continue
            
        # Find a keyword to remove (preferably a noun or longer word)
        candidate_words = [(i, word) for i, word in enumerate(words) 
                         if len(word) > 4 and word.lower() not in ['which', 'where', 'these', 'those', 'their', 'about']]
        
        if not candidate_words:
            continue
            
        # Choose a random candidate
        idx, target_word = random.choice(candidate_words)
        
        # Create the question by removing the word
        question_words = words.copy()
        question_words[idx] = "______"
        question = " ".join(question_words)
        
        # Create options (1 correct + 3 distractors)
        options = [target_word]
        
        # Add some distractor options
        distractors = ["option", "example", "answer", "choice", "selection", "concept", "term"]
        for _ in range(3):
            if len(distractors) > 0:
                distractor = distractors.pop(0)
                options.append(distractor)
            else:
                options.append(f"Not {target_word}")
        
        # Shuffle options
        random.shuffle(options)
        
        # Track correct answer
        correct_answer = options.index(target_word)
        
        mcq = {
            "question": f"Fill in the blank: {question}",
            "options": options,
            "correct_answer": options[correct_answer]
        }
        
        mcqs.append(mcq)
    
    if not mcqs:
        # Last resort - create a completely generic MCQ
        generic_mcq = {
            "question": "What is the main topic of this text?",
            "options": ["Education", "Science", "Technology", "History"],
            "correct_answer": "Education"
        }
        mcqs.append(generic_mcq)
    
    return {"mcqs": mcqs}

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    data = request.json
    answers = data.get('answers', {})

    # For now, return a dummy response
    return jsonify({
        "correct": len(answers),  # Number of correct answers
        "total": len(answers)     # Total number of questions
    })

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.json
    user_message = data.get('message', '').strip()
    character = data.get('character', 'Suzie')
    language = data.get('language', 'en')
    include_images = data.get('include_images', True)  # Default to True

    app.logger.info(f"Chat request: message='{user_message}', character='{character}', language='{language}', include_images={include_images}")

    # Handle special "greeting" message type
    if user_message.lower() == "greeting":
        app.logger.info("Processing greeting request")
        # Generate greeting based on language
        greetings = {
            "en": f"Welcome back! How can I help you today, {session.get('registered_name', 'User')}?",
            "es": f"¡Bienvenido de nuevo! ¿Cómo puedo ayudarte hoy, {session.get('registered_name', 'User')}?",
            "fr": f"Bienvenue! Comment puis-je vous aider aujourd'hui, {session.get('registered_name', 'User')}?",
            "de": f"Willkommen zurück! Wie kann ich dir heute helfen, {session.get('registered_name', 'User')}?",
            "ja": f"おかえりなさい！今日はどのようにお手伝いできますか、{session.get('registered_name', 'User')}さん？",
            "zh": f"欢迎回来！今天我能帮你什么，{session.get('registered_name', 'User')}？",
            "hi": f"वापस आने पर स्वागत है! आज मैं आपकी कैसे मदद कर सकता हूँ, {session.get('registered_name', 'User')}?",
            "ar": f"مرحبا بعودتك! كيف يمكنني مساعدتك اليوم, {session.get('registered_name', 'User')}؟",
            "ru": f"Добро пожаловать обратно! Чем я могу помочь вам сегодня, {session.get('registered_name', 'User')}?"
        }
        
        greeting_text = greetings.get(language, greetings["en"])
        
        # Generate speech for greeting
        try:
            audio_path = generate_speech(greeting_text, character, language)
            app.logger.info(f"Generated greeting audio: {audio_path}")
        except Exception as e:
            app.logger.error(f"Error generating greeting audio: {e}")
            audio_path = None
            
        # Return just the audio path for greeting
        return jsonify({
            "response": greeting_text,
            "audio": audio_path,
            "character": character
        })

    if not user_message:
        return jsonify({
            "response": "Please enter a message.",
            "error": "Empty message"
        })
    
    # Check if session was previously ended due to restricted content
    session_status = session.get('chat_session_status', 'active')
    
    # If we're starting a new message but the previous session was ended
    if session_status == 'ended':
        # Reset the session
        session['chat_session_status'] = 'active'

    # Check for restricted topics
    if is_restricted_topic(user_message) or contains_inappropriate_content(user_message):
        # Track this for analytics (safely)
        try:
            restricted_query = RestrictedQuery(user_id=current_user.id, query=user_message)
            db.session.add(restricted_query)
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Failed to log restricted query: {e}")
            db.session.rollback()
        
        # Send email notification if configured
        try:
            subject = "Restricted Topic Accessed"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background-color: #e74c3c; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                    <h1 style="color: white; margin: 0;">⚠️ Restricted Content Alert ⚠️</h1>
                </div>
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                    <p>Dear {session.get('registered_name', 'Parent/Guardian')},</p>
                    
                    <div style="background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 5px solid #e74c3c;">
                        <h2 style="margin: 0; font-size: 18px;">Content Access Notice</h2>
                        <p style="margin: 10px 0 0 0;">User '{session.get('registered_name', 'Unknown User')}' attempted to access content related to restricted topics.</p>
                    </div>
                    
                    <div style="background-color: #f2f2f2; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; font-weight: bold;">Query Reference:</p>
                        <p style="margin: 10px 0 0 0; font-style: italic;">"{user_message}"</p>
                    </div>
                    
                    <p>The session has been flagged and educational content access has been limited until next login.</p>
                    <p>If you believe this is a mistake, please discuss appropriate educational topics with the user.</p>
                    
                    <div style="text-align: center; margin: 25px 0;">
                        <a href="{request.host_url}" style="background-color: #e74c3c; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Review Account Activity</a>
                    </div>
                    
                    <p>Best regards,<br>Anime Educational Chatbot Team</p>
                </div>
                <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                    <p>© 2023 Anime Educational Chatbot</p>
                </div>
            </body>
            </html>
            """
            
            send_email_notification(subject, body)
        except Exception as email_error:
            app.logger.error(f"Failed to send restriction notification email: {email_error}")
        
        # End the session
        session['chat_session_status'] = 'ended'
        
        # Prepare response based on selected language
        restricted_responses = {
            "en": "I'm sorry, but that topic is not appropriate for an educational setting. Please ask about school subjects like math, science, history, or literature instead.",
            "es": "Lo siento, pero ese tema no es apropiado para un entorno educativo. Por favor, pregunta sobre materias escolares como matemáticas, ciencias, historia o literatura.",
            "fr": "Je suis désolé, mais ce sujet n'est pas approprié pour un cadre éducatif. Veuillez plutôt poser des questions sur des matières scolaires comme les mathématiques, les sciences, l'histoire ou la littérature.",
            "de": "Es tut mir leid, aber dieses Thema ist für ein Bildungsumfeld nicht geeignet. Bitte frage stattdessen nach Schulfächern wie Mathematik, Naturwissenschaften, Geschichte oder Literatur.",
            "ja": "申し訳ありませんが、そのトピックは教育の場にふさわしくありません。数学、科学、歴史、文学などの学校の科目について質問してください。",
            "zh": "对不起，该主题不适合教育环境。请询问数学、科学、历史或文学等学校科目。",
            "hi": "मुझे खेद है, लेकिन वह विषय शैक्षिक वातावरण के लिए उपयुक्त नहीं है। कृपया गणित, विज्ञान, इतिहास, या साहित्य जैसे स्कूल विषयों के बारे में पूछें।",
            "ar": "أنا آسف، ولكن هذا الموضوع غير مناسب للإعداد التعليمي. يرجى السؤال عن المواد المدرسية مثل الرياضيات أو العلوم أو التاريخ أو الأدب بدلاً من ذلك.",
            "ru": "Мне жаль, но эта тема не подходит для образовательной среды. Пожалуйста, спрашивайте о школьных предметах, таких как математика, наука, история или литература."
        }
        
        restricted_response = restricted_responses.get(language, restricted_responses["en"])
        
        # Return response indicating restrictions
        return jsonify({
            "response": restricted_response,
            "audio": None,
            "images": ["/static/default-avatar.png"],
            "is_restricted": True,
            "end_session": True
        })

    # Regular response path
    try:
        # Translate user message to English for processing if it's not in English
        original_language = language
        translated_user_message = user_message
        
        # Get response from language model based on user message
        response_text = get_response(translated_user_message, "")
        app.logger.info(f"Generated response: {response_text[:50]}...")
        
        # Translate response back to the selected language if it's not English
        if original_language != "en":
            try:
                app.logger.info(f"Translating response to {original_language}")
                translated_response = translate_text(response_text, source_language="en", target_language=original_language)
                if translated_response:
                    response_text = translated_response
                    app.logger.info(f"Translated response: {response_text[:50]}...")
            except Exception as translate_error:
                app.logger.error(f"Error translating response: {translate_error}")
        
        # If include_images flag is true, fetch relevant images
        images = ["/static/default-avatar.png"]  # Default fallback image
        if include_images:
            try:
                # Create a more specific search query
                image_query = generate_image_search_query(user_message)
                app.logger.info(f"Fetching images for query: '{image_query}'")
                images = fetch_images_for_query(image_query)
                
                # If real images can't be fetched, use topic-specific placeholder images
                if not images or (len(images) == 1 and "default-avatar.png" in images[0]):
                    app.logger.info("Using topic-based images instead of real ones")
                    
                    # Determine topic from query
                    query_lower = user_message.lower()
                    if any(word in query_lower for word in ['math', 'number', 'equation', 'calculation']):
                        images = ["/static/images/educational/math.jpg"]
                    elif any(word in query_lower for word in ['science', 'physics', 'chemistry', 'biology']):
                        images = ["/static/images/educational/science.jpg"]
                    elif any(word in query_lower for word in ['history', 'ancient', 'past']):
                        images = ["/static/images/educational/history.jpg"]
                    elif any(word in query_lower for word in ['space', 'planet', 'star']):
                        images = ["/static/images/educational/space.jpg"]
                    elif any(word in query_lower for word in ['computer', 'programming', 'code']):
                        images = ["/static/images/educational/computer.jpg"]
                    elif any(word in query_lower for word in ['art', 'music', 'painting']):
                        images = ["/static/images/educational/art.jpg"]
                    else:
                        images = ["/static/default-avatar.png"]
                
                app.logger.info(f"Final images: {images}")
            except Exception as img_error:
                app.logger.error(f"Error getting images: {img_error}")
                images = ["/static/default-avatar.png"]
        
        # Generate text-to-speech audio
        audio_path = None
        try:
            # Generate speech in the selected language
            audio_path = generate_speech(response_text, character, language)
            app.logger.info(f"Generated audio at path: {audio_path}")
        except Exception as e:
            app.logger.error(f"Error generating speech: {e}")
        
        # Generate educational links for the query
        links = generate_educational_links(user_message)
        
        # Store the message in database (best effort)
        try:
            user_msg = ChatMessage(user_id=current_user.id, role='user', message=user_message)
            db.session.add(user_msg)
            
            try:
                bot_msg = ChatMessage(user_id=current_user.id, role='bot', message=response_text)
                db.session.add(bot_msg)
                db.session.commit()
            except Exception as db_error:
                app.logger.error(f"Could not save messages to database: {db_error}")
                db.session.rollback()
        except Exception as e:
            app.logger.error(f"Error with database operations: {e}")
            # Continue execution even if database operations fail
            
        # Return response with all requested elements
        return jsonify({
            "response": response_text,
            "audio": audio_path,
            "images": images,
            "links": links,
            "character": character
        })
    except Exception as e:
        app.logger.error(f"Error in chat route: {e}")
        # Always return a response even if processing fails
        
        # Get error message in the selected language
        error_messages = {
            "en": "I apologize, but I'm having trouble right now. Could you try again in a moment?",
            "es": "Me disculpo, pero estoy teniendo problemas en este momento. ¿Podrías intentarlo de nuevo en un momento?",
            "fr": "Je m'excuse, mais j'ai des difficultés en ce moment. Pourriez-vous réessayer dans un instant?",
            "de": "Ich entschuldige mich, aber ich habe gerade Schwierigkeiten. Könntest du es in einem Moment noch einmal versuchen?",
            "ja": "申し訳ありませんが、今問題が発生しています。少し後でもう一度お試しいただけますか？",
            "zh": "抱歉，我现在遇到了问题。请稍后再试好吗？",
            "hi": "मैं क्षमा चाहता हूं, लेकिन मुझे अभी परेशानी हो रही है। क्या आप एक क्षण में फिर से कोशिश कर सकते हैं?",
            "ar": "أعتذر، لكنني أواجه مشكلة الآن. هل يمكنك المحاولة مرة أخرى بعد قليل؟",
            "ru": "Приношу извинения, но у меня сейчас проблемы. Не могли бы вы попробовать еще раз через мгновение?"
        }
        
        error_message = error_messages.get(language, error_messages["en"])
        
        return jsonify({
            "response": error_message,
            "error": str(e)
        })

@app.route('/progress')
def progress():
    # check if user is logged in
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    try:
        # get user progress data
        progress_data = {
            'total_chats': ChatMessage.query.filter_by(user_id=current_user.id).count(),
            'quiz_score': current_user.quiz_score or 0,
            'games_played': current_user.games_played or 0,
            'learning_time': current_user.learning_time or 0
        }
        
        # get recent chat history
        recent_chats = ChatMessage.query.filter_by(user_id=current_user.id)\
            .order_by(ChatMessage.timestamp.desc())\
            .limit(5)\
            .all()
            
        return render_template('progress.html', 
                             progress=progress_data,
                             recent_chats=recent_chats)
                             
    except Exception as e:
        # handle database errors
        flash('Error loading progress data. Please try again later.', 'error')
        return redirect(url_for('progress_tracker'))

@app.route('/update_progress', methods=['POST'])
def update_progress():
    # check if user is logged in
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not authenticated'}), 401
        
    try:
        # get progress data from request
        data = request.get_json()
        quiz_score = data.get('quiz_score', 0)
        games_played = data.get('games_played', 0)
        learning_time = data.get('learning_time', 0)
        
        # update user progress
        current_user.quiz_score = quiz_score
        current_user.games_played = games_played 
        current_user.learning_time = learning_time
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        # handle update errors
        return jsonify({'error': 'Failed to update progress'}), 500

@app.route('/sync_progress', methods=['POST'])
def sync_progress():
    # check if user is logged in
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not authenticated'}), 401
        
    try:
        # Ensure database structure is correct before proceeding
        ensure_db_structure()
        
        # get sync data from request
        data = request.get_json() or {}
        
        # Log received data for debugging
        app.logger.info(f"Received sync data: {data}")
        
        # update user progress in database - only update fields that are provided
        if 'learning_progress' in data:
            current_user.learning_progress = data.get('learning_progress')
        if 'goals' in data:
            current_user.goals = data.get('goals')
        if 'daily_contributions' in data:
            current_user.daily_contributions = data.get('daily_contributions')
        if 'unlocked_badges' in data:
            current_user.unlocked_badges = data.get('unlocked_badges')
        if 'current_streak' in data:
            current_user.current_streak = data.get('current_streak')
        if 'best_streak' in data:
            current_user.best_streak = data.get('best_streak')
        if 'total_contributions' in data:
            current_user.total_contributions = data.get('total_contributions')
        if 'daily_notes' in data:
            try:
                # Validate that daily_notes is a valid JSON string if needed
                if isinstance(data.get('daily_notes'), str):
                    # Try to parse it to make sure it's valid JSON
                    json.loads(data.get('daily_notes'))
                current_user.daily_notes = data.get('daily_notes')
            except json.JSONDecodeError:
                app.logger.error(f"Invalid daily_notes JSON format: {data.get('daily_notes')}")
                return jsonify({'error': 'Invalid daily_notes format'}), 400
        
        db.session.commit()
        
        # Get daily_notes safely
        try:
            daily_notes = current_user.daily_notes
        except Exception as e:
            app.logger.error(f"Error retrieving daily_notes: {str(e)}")
            daily_notes = '[]'
        
        # Return all user data
        response_data = {
            'success': True,
            'learning_progress': current_user.learning_progress,
            'goals': current_user.goals,
            'daily_contributions': current_user.daily_contributions,
            'unlocked_badges': current_user.unlocked_badges,
            'current_streak': current_user.current_streak,
            'best_streak': current_user.best_streak,
            'total_contributions': current_user.total_contributions,
            'daily_notes': daily_notes
        }
        
        return jsonify(response_data)
    except Exception as e:
        # handle sync errors
        app.logger.error(f"Failed to sync progress: {str(e)}")
        return jsonify({'error': f'Failed to sync progress: {str(e)}'}), 500

@app.route('/send_achievement_email', methods=['POST'])
@login_required
def send_achievement_email():
    try:
        # Get achievement data from request
        data = request.get_json()
        achievement_name = data.get('achievement')
        
        if not achievement_name:
            return jsonify({'error': 'Achievement name is required'}), 400
            
        # Create email content
        subject = f"Achievement Unlocked: {achievement_name}!"
        
        # Customize message based on achievement
        achievement_descriptions = {
            'Math Wizard': 'You successfully solved the math challenge.',
            'Chatbot Master': 'You\'ve sent at least 10 messages to the chatbot.',
            'Quiz Champion': 'You\'ve completed 5 quizzes.',
            'Explorer': 'You\'ve visited all sections of the app.',
            'Science Genius': 'You\'ve completed the science challenge.',
            'Math Master': 'You\'ve completed 10 math questions correctly.'
        }
        
        description = achievement_descriptions.get(achievement_name, 'You\'ve unlocked a new achievement!')
        
        # Email content with HTML formatting
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #8e44ad; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">🏆 Achievement Unlocked! 🏆</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                <p>Congratulations {current_user.name or current_user.username}!</p>
                <div style="background-color: #8e44ad; color: white; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                    <h2 style="margin: 0;">{achievement_name}</h2>
                    <p style="margin: 10px 0 0 0;">{description}</p>
                </div>
                <p>Keep up the great work on your learning journey!</p>
                <p>What will you achieve next? Log in to see your progress and unlock more achievements.</p>
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{request.host_url}" style="background-color: #8e44ad; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Continue Learning</a>
                </div>
                <p>Best regards,<br>The Anime Educational Chatbot Team</p>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                <p>© 2023 Anime Educational Chatbot</p>
            </div>
        </body>
        </html>
        """
        
        # Send email
        send_email_notification(subject, body)
        
        return jsonify({'success': True, 'message': 'Achievement email sent successfully'})
        
    except Exception as e:
        app.logger.error(f"Failed to send achievement email: {e}")
        return jsonify({'error': 'Failed to send achievement email'}), 500

@app.route('/check_achievements', methods=['POST'])
@login_required
def check_achievements():
    try:
        # Get any existing achievements
        current_achievements = json.loads(current_user.unlocked_badges or '{}')
        
        # Get user stats
        data = request.get_json()
        task_type = data.get('task_type')
        task_data = data.get('task_data', {})
        
        # Initialize the response
        response = {
            'new_achievements': [],
            'success': True
        }
        
        # Check for achievement conditions based on task type
        if task_type == 'chatbot_message':
            # Check if user has sent at least 10 messages and doesn't already have the badge
            message_count = ChatMessage.query.filter_by(user_id=current_user.id, role='user').count()
            if message_count >= 10 and 'chatbotMaster' not in current_achievements:
                current_achievements['chatbotMaster'] = True
                response['new_achievements'].append('Chatbot Master')
                
        elif task_type == 'quiz_complete':
            # Check quiz completion achievement
            quiz_count = current_user.quiz_score or 0
            if quiz_count >= 5 and 'quizChampion' not in current_achievements:
                current_achievements['quizChampion'] = True
                response['new_achievements'].append('Quiz Champion')
                
        elif task_type == 'math_challenge':
            # Check math challenge achievement
            if 'mathWizard' not in current_achievements:
                current_achievements['mathWizard'] = True
                response['new_achievements'].append('Math Wizard')
                
        elif task_type == 'section_visit':
            # Track visited sections
            visited_sections = task_data.get('visited_sections', [])
            required_sections = ['chat', 'quiz', 'progress', 'games']
            
            # Check if all required sections have been visited
            all_visited = all(section in visited_sections for section in required_sections)
            if all_visited and 'explorer' not in current_achievements:
                current_achievements['explorer'] = True
                response['new_achievements'].append('Explorer')
                
        elif task_type == 'science_challenge':
            # Check science challenge achievement
            if 'scienceGenius' not in current_achievements:
                current_achievements['scienceGenius'] = True
                response['new_achievements'].append('Science Genius')
                
        elif task_type == 'math_questions':
            # Check math questions achievement
            math_correct = task_data.get('correct_count', 0)
            if math_correct >= 10 and 'mathMaster' not in current_achievements:
                current_achievements['mathMaster'] = True
                response['new_achievements'].append('Math Master')
        
        # Save updated achievements to database
        if response['new_achievements']:
            current_user.unlocked_badges = json.dumps(current_achievements)
            db.session.commit()
            
            # Send an email for each new achievement
            for achievement in response['new_achievements']:
                # Call the send_achievement_email function
                subject = f"Achievement Unlocked: {achievement}!"
                # Customize message based on achievement
                achievement_descriptions = {
                    'Math Wizard': 'You successfully solved the math challenge.',
                    'Chatbot Master': 'You\'ve sent at least 10 messages to the chatbot.',
                    'Quiz Champion': 'You\'ve completed 5 quizzes.',
                    'Explorer': 'You\'ve visited all sections of the app.',
                    'Science Genius': 'You\'ve completed the science challenge.',
                    'Math Master': 'You\'ve completed 10 math questions correctly.'
                }
                
                description = achievement_descriptions.get(achievement, 'You\'ve unlocked a new achievement!')
                
                # Email content with HTML formatting
                body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #8e44ad; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                        <h1 style="color: white; margin: 0;">🏆 Achievement Unlocked! 🏆</h1>
                    </div>
                    <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                        <p>Congratulations {current_user.name or current_user.username}!</p>
                        <div style="background-color: #8e44ad; color: white; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0;">
                            <h2 style="margin: 0;">{achievement}</h2>
                            <p style="margin: 10px 0 0 0;">{description}</p>
                        </div>
                        <p>Keep up the great work on your learning journey!</p>
                        <p>What will you achieve next? Log in to see your progress and unlock more achievements.</p>
                        <div style="text-align: center; margin: 25px 0;">
                            <a href="{request.host_url}" style="background-color: #8e44ad; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Continue Learning</a>
                        </div>
                        <p>Best regards,<br>The Anime Educational Chatbot Team</p>
                    </div>
                    <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                        <p>© 2023 Anime Educational Chatbot</p>
                    </div>
                </body>
                </html>
                """
                
                send_email_notification(subject, body)
        
        return jsonify(response)
        
    except Exception as e:
        app.logger.error(f"Failed to check achievements: {e}")
        return jsonify({'error': 'Failed to check achievements', 'success': False}), 500

def full_cleanup():
    print("Performing cleanup on server shutdown...")
    audio_dir = os.path.join('static', 'audio')
    if os.path.exists(audio_dir):
        files = glob.glob(f"{audio_dir}/*.mp3")
        for file in files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error deleting file {file}: {e}")
        print(f"Deleted {len(files)} temporary audio files!")

    upload_dir = "uploads"
    if os.path.exists(upload_dir):
        files = glob.glob(f"{upload_dir}/*")
        for file in files:
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error deleting file {file}: {e}")
        print(f"Deleted {len(files)} uploaded files!")

# Move this function **below** full_cleanup()
def handle_shutdown(signum, frame):
    print("Shutting down gracefully...")
    full_cleanup()  # Now, it's defined correctly
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# Database initialization command
@app.cli.command("init-db")
def init_db_command():
    """Create the database tables."""
    try:
        # Create database if it doesn't exist
        with mysql.connector.connect(
            host="localhost",
            port=3306,
            user="root",
            password=""
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE DATABASE IF NOT EXISTS anime_educational")
        
        # Create tables
        db.create_all()
        print("Initialized the database.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def ensure_db_structure():
    """Ensure database has all required columns"""
    try:
        app.logger.info("Checking database structure...")
        
        # First, check if tables exist
        with db.engine.connect() as conn:
            try:
                # Check if User table exists
                users_exist = conn.execute(text("SELECT 1 FROM user LIMIT 1"))
                app.logger.info("User table exists")
            except Exception as e:
                app.logger.warning(f"User table check failed: {e}")
                # Create tables if they don't exist
                db.create_all()
                app.logger.info("Created database tables")
                return
                
        # Check ChatMessage table structure
        with db.engine.connect() as conn:
            try:
                # Check if response column exists in ChatMessage
                conn.execute(text("SELECT response FROM chat_message LIMIT 1"))
                app.logger.info("response column exists in ChatMessage table")
            except Exception as e:
                app.logger.warning(f"ChatMessage.response column missing: {e}")
                try:
                    # Add the response column
                    conn.execute(text("ALTER TABLE chat_message ADD COLUMN response TEXT NULL"))
                    conn.commit()
                    app.logger.info("Added response column to ChatMessage table")
                except Exception as add_e:
                    app.logger.error(f"Failed to add response column: {add_e}")
        
        # List of columns to check and add if missing
        columns_to_check = {
            'profile_frame': "VARCHAR(100) DEFAULT 'default'",
            'daily_notes': "TEXT DEFAULT '[]'",
            'unlocked_badges': "TEXT DEFAULT '{}'",
            'daily_contributions': "TEXT DEFAULT '{}'",
            'unlocked_frames': "TEXT DEFAULT '[]'",
            'recovery_email': "VARCHAR(120) DEFAULT NULL",
            'name': "VARCHAR(100) DEFAULT NULL",
            'age': "INTEGER DEFAULT NULL",
            'profile_pic': "VARCHAR(200) DEFAULT 'profile_pics/default-avatar.png'",
            'current_streak': "INTEGER DEFAULT 0",
            'best_streak': "INTEGER DEFAULT 0",
            'total_contributions': "INTEGER DEFAULT 0",
            'quiz_score': "INTEGER DEFAULT 0",
            'games_played': "INTEGER DEFAULT 0",
            'learning_time': "INTEGER DEFAULT 0"
        }
            
        # Check if each column exists in the User model
        for column, data_type in columns_to_check.items():
            try:
                # Try to query the column to check if it exists
                db.session.execute(db.select(getattr(User, column)).limit(1))
                app.logger.info(f"{column} column exists in User table")
            except Exception as e:
                app.logger.warning(f"{column} column does not exist in User table: {e}")
                # Add column if it doesn't exist
                try:
                    with db.engine.connect() as conn:
                        conn.execute(text(f"ALTER TABLE user ADD COLUMN {column} {data_type}"))
                        conn.commit()
                    app.logger.info(f"Added {column} column to User table")
                except Exception as add_e:
                    app.logger.error(f"Failed to add {column} column: {add_e}")
    
        return True
    except Exception as e:
        app.logger.error(f"Error in ensure_db_structure: {e}")
        return False

# Initialize the database structure at startup - this needs to happen before routes are accessed
with app.app_context():
    # First create basic tables
    db.create_all()
    # Then ensure all required columns exist
    ensure_db_structure()
    
    # Create default profile pics directory if it doesn't exist
    profile_pics_dir = os.path.join('static', 'profile_pics')
    if not os.path.exists(profile_pics_dir):
        os.makedirs(profile_pics_dir)
    # Ensure default avatar exists
    default_avatar = os.path.join('static', 'default-avatar.png')
    if not os.path.exists(default_avatar):
        # Create a simple avatar or copy from another location
        try:
            # If user-avatar.png exists, copy it as default
            user_avatar = os.path.join('static', 'user-avatar.png')
            if os.path.exists(user_avatar):
                import shutil
                shutil.copy(user_avatar, default_avatar)
        except:
            print("Could not create default avatar. Please ensure a default profile image exists.")

# Create a default admin user
@app.cli.command("create-admin")
def create_admin():
    """Create a default admin user."""
    admin = User.query.filter_by(username="admin").first()
    if admin is None:
        admin = User(
            username="admin",
            email="admin@example.com",
            name="Administrator",
            is_admin=True
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("Created admin user.")
    else:
        print("Admin user already exists.")

# Add admin route
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('login'))
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Check if email exists
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No account found with that email address.', 'error')
            return redirect(url_for('forgot_password'))
        
        # Generate password reset token
        token = serializer.dumps(email, salt='password-reset-salt')
        
        # Create password reset link
        reset_url = url_for('reset_password', token=token, _external=True)
        
        # Email content
        subject = "Password Reset Request - Anime Educational Chatbot"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #004754; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Password Reset</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                <p>Hello {user.name},</p>
                <p>We received a request to reset your password for your Anime Educational Chatbot account.</p>
                <p>To reset your password, please click the button below:</p>
                <div style="text-align: center; margin: 25px 0;">
                    <a href="{reset_url}" style="background-color: #bebd00; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Reset Password</a>
                </div>
                <p>If you did not request a password reset, please ignore this email or contact support if you have questions.</p>
                <p>This link will expire in 60 minutes.</p>
                <p>Best regards,<br>The Anime Educational Chatbot Team</p>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                <p>© 2023 Anime Educational Chatbot</p>
            </div>
        </body>
        </html>
        """
        
        # Send email
        try:
            send_email_notification(subject, body)
            flash('Password reset instructions have been sent to your email.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Failed to send reset email: {e}")
            flash('Failed to send reset email. Please try again later.', 'error')
            return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # Verify token (valid for 60 minutes = 3600 seconds)
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except:
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('forgot_password'))
    
    # Find user by email
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate password
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters long.', 'error')
            return render_template('reset_password.html', token=token)
        
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)
        
        # Update user's password
        user.set_password(password)
        db.session.commit()
        
        # Send confirmation email
        subject = "Password Reset Successful - Anime Educational Chatbot"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #004754; padding: 15px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Password Updated</h1>
            </div>
            <div style="background-color: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px;">
                <p>Hello {user.name},</p>
                <p>Your password has been successfully updated.</p>
                <p>If you did not make this change, please contact our support team immediately.</p>
                <p>Best regards,<br>The Anime Educational Chatbot Team</p>
            </div>
            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                <p>© 2023 Anime Educational Chatbot</p>
            </div>
        </body>
        </html>
        """
        send_email_notification(subject, body)
        
        flash('Your password has been updated! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)

@app.route('/database-test')
@login_required
def database_test():
    """A diagnostic route that checks database connectivity and user authentication."""
    if not current_user.is_admin:
        flash('Only administrators can access this page.', 'error')
        return redirect(url_for('login'))
    
    db_info = {
        'connection_uri': app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1],  # Hide credentials
        'db_type': 'MySQL' if 'mysql' in app.config['SQLALCHEMY_DATABASE_URI'] else 'SQLite',
        'users_count': User.query.count(),
        'messages_count': ChatMessage.query.count(),
        'current_user': {
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'is_admin': current_user.is_admin,
            'has_password_hash': bool(current_user.password_hash),
            'hash_length': len(current_user.password_hash or '') if current_user.password_hash else 0
        }
    }
    
    # Attempt to get all users (limited to 10)
    try:
        users = User.query.limit(10).all()
        user_list = [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'has_password': bool(user.password_hash),
        } for user in users]
        db_info['user_sample'] = user_list
    except Exception as e:
        db_info['user_sample_error'] = str(e)
    
    return render_template('database_test.html', db_info=db_info)

def get_cohere_response(query, context=""):
    """Get response from Cohere API with improved error handling"""
    try:
        app.logger.info(f"Getting response from Cohere for: '{query[:50]}...'")
        
        # Process context to avoid exceeding token limits
        if context:
            # Simple truncation to avoid very long contexts
            context = context[-2000:] if len(context) > 2000 else context
        
        # Call Cohere API with updated syntax to match current API version
        try:
            # Try the chat API format first (newer versions)
            response = cohere_client.chat(
                message=query,
                model="command", # Using command model for educational content
                temperature=0.7,  # Balanced creativity
                prompt_truncation="AUTO",
                stream=False,
                citation_quality="accurate",
                preamble=(
                    "You are an educational anime chatbot assistant for children. "
                    "Provide informative, age-appropriate responses with educational content. "
                    "Include facts, examples, and explanations suitable for learning. "
                    f"Previous conversation context: {context}"
                ),
            )
            
            # Process response from the chat API
            response_text = response.text
            
        except (AttributeError, TypeError) as api_format_error:
            app.logger.warning(f"Chat API format error: {api_format_error}, trying generate API instead")
            
            # Fall back to generate API format (older versions)
            response = cohere_client.generate(
                model="command",
                prompt=f"You are an educational anime chatbot assistant for children. Provide informative, age-appropriate responses with educational content. Previous conversation context: {context}\n\nUser: {query}\nChatbot:",
                max_tokens=300,
                temperature=0.7,
                k=0,
                stop_sequences=["\n\n"],
                return_likelihoods="NONE"
            )
            
            # Access the response text correctly from generate API
            response_text = response.generations[0].text.strip()
        
        # Clean and format response for better presentation
        response_text = response_text.replace("\n\n", "\n").strip()
        
        app.logger.info(f"Received response from Cohere: '{response_text[:50]}...'")
        return response_text
        
    except Exception as e:
        app.logger.error(f"Error getting Cohere response: {e}")
        # Fallback response in case of API failure
        return "I'm having trouble connecting to my knowledge base right now. Please try asking your question again in a moment."

def fetch_educational_links(query):
    """Fetch safe educational links related to the query."""
    try:
        app.logger.info(f"Fetching educational links for: {query}")
        
        # List of educational domains to prioritize
        educational_domains = [
            'khanacademy.org', 'britannica.com', 'nationalgeographic.com', 'nasa.gov',
            'pbs.org', 'history.com', 'howstuffworks.com', 'sciencemuseum.org.uk',
            'exploratorium.edu', 'amnh.org', 'kids.nationalgeographic.com',
            'education.com', 'dkfindout.com', 'factmonster.com', 'coolmath.com'
        ]
        
        # Extract key educational terms from the query
        query_terms = query.lower().split()
        educational_keywords = []
        
        # Remove common question words and prepositions
        stop_words = ['what', 'why', 'how', 'when', 'where', 'who', 'is', 'are', 'do', 'does', 
                      'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'about']
        
        # Filter out stop words
        for term in query_terms:
            if term not in stop_words and len(term) > 2:
                educational_keywords.append(term)
        
        # Create search query with edu focus
        search_query = f"{' '.join(educational_keywords)} educational resource for students"
        
        # Simulate fetching results (in a real implementation, you would call an API)
        # Here we're creating sample data based on the query
        links = []
        
        # Add subject-specific links based on query keywords
        if any(word in query.lower() for word in ['science', 'biology', 'chemistry', 'physics']):
            links.append({
                "title": "Science for Kids - National Geographic",
                "url": "https://kids.nationalgeographic.com/science"
            })
            links.append({
                "title": "Science - Khan Academy",
                "url": "https://www.khanacademy.org/science"
            })
            
        if any(word in query.lower() for word in ['math', 'calculation', 'number', 'equation']):
            links.append({
                "title": "Math Games and Activities - Coolmath",
                "url": "https://www.coolmath.com"
            })
            links.append({
                "title": "Mathematics - Khan Academy",
                "url": "https://www.khanacademy.org/math"
            })
            
        if any(word in query.lower() for word in ['history', 'ancient', 'past', 'civilization']):
            links.append({
                "title": "History for Kids - DK Find Out",
                "url": "https://www.dkfindout.com/us/history"
            })
            links.append({
                "title": "History - BBC Bitesize",
                "url": "https://www.bbc.co.uk/bitesize/subjects/zk26n39"
            })
            
        if any(word in query.lower() for word in ['space', 'planet', 'star', 'galaxy', 'universe']):
            links.append({
                "title": "Space - NASA Space Place",
                "url": "https://spaceplace.nasa.gov"
            })
            links.append({
                "title": "Space Facts for Kids",
                "url": "https://www.planetsforkids.org"
            })
        
        # Add general educational links if no specific ones were found
        if not links:
            links = [
                {"title": "Khan Academy", "url": "https://www.khanacademy.org"},
                {"title": "National Geographic Kids", "url": "https://kids.nationalgeographic.com"},
                {"title": "Smithsonian Learning Lab", "url": "https://learninglab.si.edu"},
                {"title": "PBS Kids", "url": "https://pbskids.org"},
                {"title": "Britannica Kids", "url": "https://kids.britannica.com"}
            ]
        
        app.logger.info(f"Found {len(links)} educational links")
        return links
    
    except Exception as e:
        app.logger.error(f"Error fetching educational links: {e}")
        return []

def generate_image_search_query(query):
    """Generate a better image search query from the user message"""
    try:
        # Remove common question words and prepositions
        common_words = ['what', 'why', 'how', 'when', 'where', 'who', 'is', 'are', 'do', 'does', 'will', 
                     'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'about', 'can', 'could']
        
        # Convert to lowercase and tokenize
        query_words = query.lower().split()
        
        # Remove common question words
        filtered_words = [word for word in query_words if word not in common_words]
        
        # If query is too short after filtering, use original
        if len(filtered_words) < 2:
            filtered_words = query_words
            
        # Extract key terms (up to 5 words)
        key_terms = filtered_words[:5] if len(filtered_words) > 5 else filtered_words
        
        # Generate a more specific search query
        search_query = " ".join(key_terms) + " illustration educational"
        
        app.logger.info(f"Generated image search query: '{search_query}' from '{query}'")
        return search_query
        
    except Exception as e:
        app.logger.error(f"Error generating image search query: {e}")
        return query

def fetch_images_for_query(query):
    """Fetch images for a specific query with educational focus"""
    try:
        app.logger.info(f"Fetching images for query: '{query}'")
        
        # Images that we know exist in most systems
        default_images = [
            "static/default-avatar.png",  # Always use default avatar as fallback
        ]
        
        # Try to fetch real images first using Google Custom Search API
        try:
            search_results = fetch_google_results(query, search_type="image")
            if 'items' in search_results and len(search_results['items']) > 0:
                # Get image URLs from search results
                image_urls = [item.get('link') for item in search_results['items'] if 'link' in item]
                
                # Filter for safe images
                safe_image_urls = filter_safe_images(image_urls)
                
                if safe_image_urls:
                    app.logger.info(f"Successfully found {len(safe_image_urls)} images for query")
                    return safe_image_urls
        except Exception as search_error:
            app.logger.error(f"Error fetching images from search API: {search_error}")
        
        # If search fails or returns no results, return default images
        return default_images
        
    except Exception as e:
        app.logger.error(f"Error in fetch_images_for_query: {e}")
        return ["static/default-avatar.png"]  # Use avatar image as ultimate fallback

def generate_educational_links(query):
    """Generate relevant educational links for a query including Wikipedia and YouTube"""
    try:
        app.logger.info(f"Generating educational links for: {query}")
        
        # Clean the query for URL use
        clean_query = query.replace(' ', '+')
        
        # Create standard links for educational content
        wikipedia_link = {
            "title": f"Wikipedia: {query}",
            "url": f"https://en.wikipedia.org/wiki/Special:Search?search={clean_query}&go=Go"
        }
        
        youtube_link = {
            "title": f"YouTube Tutorials: {query}",
            "url": f"https://www.youtube.com/results?search_query={clean_query}+tutorial+educational"
        }
        
        khan_academy_link = {
            "title": "Khan Academy",
            "url": f"https://www.khanacademy.org/search?page_search_query={clean_query}"
        }
        
        nat_geo_link = {
            "title": "National Geographic Kids",
            "url": "https://kids.nationalgeographic.com/"
        }
        
        # Try to get more specific links based on topic
        query_lower = query.lower()
        topic_links = []
        
        if any(word in query_lower for word in ['math', 'calculation', 'number', 'equation']):
            topic_links.append({
                "title": "Math Concepts - Khan Academy",
                "url": "https://www.khanacademy.org/math"
            })
        
        if any(word in query_lower for word in ['science', 'biology', 'chemistry', 'physics']):
            topic_links.append({
                "title": "Science - Khan Academy",
                "url": "https://www.khanacademy.org/science"
            })
            
        if any(word in query_lower for word in ['history', 'past', 'ancient']):
            topic_links.append({
                "title": "History - Khan Academy",
                "url": "https://www.khanacademy.org/humanities/world-history"
            })
        
        # Combine and return all links (Wikipedia and YouTube first)
        all_links = [wikipedia_link, youtube_link] + topic_links + [khan_academy_link, nat_geo_link]
        
        # Log the links we're sending to frontend
        app.logger.info(f"Sending {len(all_links[:5])} educational links to frontend")
        for link in all_links[:5]:
            app.logger.info(f"Link: {link['title']} - {link['url']}")
            
        return all_links[:5]  # Limit to 5 links
        
    except Exception as e:
        app.logger.error(f"Error generating educational links: {e}")
        # Return basic fallback links
        return [
            {"title": "Wikipedia", "url": "https://en.wikipedia.org/"},
            {"title": "YouTube Educational", "url": "https://www.youtube.com/education"},
            {"title": "Khan Academy", "url": "https://www.khanacademy.org/"}
        ]

def is_restricted_content(text):
    """Check if content contains restricted or inappropriate material"""
    if not text:
        return False
        
    text = text.lower()
    
    # List of restricted topics and inappropriate content for a children's educational chatbot
    restricted_topics = [
        'porn', 'pornography', 'sexual', 'nude', 'naked', 'explicit',
        'violence', 'gore', 'suicide', 'self-harm', 'drugs', 'alcohol',
        'gambling', 'weapon', 'kill', 'exploit', 'abuse', 'terror',
        'extremist', 'racist', 'offensive', 'nsfw', 'adult content'
    ]
    
    # Check if any restricted topic is mentioned
    for topic in restricted_topics:
        if topic in text:
            app.logger.warning(f"Restricted content detected: '{topic}' in text")
            return True
            
    return False

# Helper function to get character name based on character ID
def get_character_name(character_id):
    character_names = {
        "Suzie": "Suzie",
        "Professor": "Professor",
        "Hikari": "Hikari",
        "Sensei": "Sensei"
    }
    return character_names.get(character_id, "Suzie")

@app.route('/create_image', methods=['GET', 'POST'])
@login_required
def create_image():
    """Create custom educational images page"""
    if request.method == 'GET':
        return render_template('create_image.html', registered_name=session.get('registered_name', 'User'))
    elif request.method == 'POST':
        try:
            data = request.get_json()
            prompt = data.get('prompt', '')
            style = data.get('style', 'realistic')
            category = data.get('category', 'science')
            
            # Check for inappropriate content
            if is_restricted_content(prompt):
                app.logger.warning(f"Restricted image prompt detected: {prompt}")
                return jsonify({
                    'error': 'Sorry, your prompt contains restricted content that is not suitable for educational purposes.'
                })
            
            # Create a more specific prompt for educational content
            safe_prompt = f"Educational {style} image about {prompt} for {category} learning, kid-friendly, non-offensive, safe for children"
            
            # For now, until we implement an actual image generation API, use pre-existing educational images
            # This would be replaced with actual API calls to image generation services
            image_urls = fetch_images_for_query(prompt)
            
            if not image_urls or len(image_urls) == 0:
                return jsonify({
                    'error': 'Could not generate an image for this prompt. Please try a different description.'
                })
            
            # Return the first image and use others as alternatives if available
            main_image = image_urls[0]
            alt_images = image_urls[1:4] if len(image_urls) > 1 else []
            
            return jsonify({
                'image_url': main_image,
                'alt_images': alt_images,
                'description': f"Educational {style} visualization of {prompt} for {category} learning.",
                'prompt': safe_prompt
            })
            
        except Exception as e:
            app.logger.error(f"Error in image generation: {e}")
            return jsonify({
                'error': 'An error occurred while generating the image. Please try again.'
            })

@app.route('/generate_speech', methods=['POST'])
@login_required
def generate_speech_endpoint():
    try:
        data = request.get_json()
        text = data.get('text', '')
        character = data.get('character', 'Suzie')
        language = data.get('language', 'en')
        
        if not text:
            return jsonify({'error': 'No text provided'}), 400
            
        # Generate speech using the existing function
        audio_path = generate_speech(text, character, language)
        
        if audio_path:
            return jsonify({
                'success': True,
                'audio_path': audio_path
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to generate speech'
            }), 500
            
    except Exception as e:
        print(f"Error in generate_speech_endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def generate_speech(text, character="Suzie", language="en"):
    try:
        # Create a unique filename for the audio
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"speech_{timestamp}_{hash(text)}.mp3"
        audio_path = os.path.join('static', 'audio', filename)
        
        # Ensure the audio directory exists
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        # Get voice configuration
        voice_config = get_voice_config(character, language)
        
        # Initialize the client
        client = texttospeech.TextToSpeechClient()
        
        # Set the text input to be synthesized
        synthesis_input = texttospeech.SynthesisInput(text=text)
        
        # Build the voice request
        voice = texttospeech.VoiceSelectionParams(
            language_code=voice_config['language_code'],
            name=voice_config['name'],
            ssml_gender=voice_config['ssml_gender']
        )
        
        # Select the type of audio file
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )
        
        # Perform the text-to-speech request
        response = client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        
        # Write the response to the output file
        with open(audio_path, "wb") as out:
            out.write(response.audio_content)
            
        return f"/static/audio/{filename}"
        
    except Exception as e:
        print(f"Error in generate_speech: {str(e)}")
        # Try fallback TTS if Google Cloud TTS fails
        try:
            return use_fallback_tts(text, character, language)
        except Exception as fallback_error:
            print(f"Fallback TTS also failed: {str(fallback_error)}")
            return None

if __name__ == '__main__':
    app.run(debug=True)
