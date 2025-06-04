# Anime Educational Chatbot 🎓

An interactive AI-powered educational chatbot that combines anime-style characters with advanced learning features. This application helps users learn various subjects through engaging conversations, quizzes, and progress tracking.

## Features 🌟

### 1. AI-Powered Learning
- Interactive chat interface with AI tutor
- Personalized learning experience
- Support for multiple subjects
- Real-time responses and explanations

### 2. User Management
- Secure user authentication
- Profile customization
- Progress tracking
- Achievement system
- Learning streaks and goals

### 3. Educational Tools
- Multiple choice quizzes
- PDF document processing
- Image recognition
- Text-to-speech capabilities
- Multi-language support

### 4. Progress Tracking
- Learning statistics
- Daily streaks
- Achievement badges
- Learning goals
- Performance analytics

### 5. Admin Features
- User management
- System monitoring
- Content moderation
- Usage statistics

## Security 🔒

The application implements multiple layers of security:
1. Master password protection
2. User authentication
3. Password hashing
4. Secure session management
5. Protected API endpoints

## Technical Stack 💻

- **Backend**: Flask (Python)
- **Database**: MySQL (with SQLite fallback)
- **AI/ML**: 
  - Cohere for natural language processing
  - Transformers for question answering
  - PyTorch for machine learning models
- **Additional Tools**:
  - PDF processing (PyPDF2, pdfminer)
  - Image processing (Pillow)
  - Text-to-speech (gTTS, Google Cloud TTS)
  - OCR (Tesseract)

## Installation 🚀

1. Clone the repository:
```bash
git clone https://github.com/yourusername/anime-educational-chatbot.git
cd anime-educational-chatbot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
Create a `.env` file with the following structure:
```
MYSQL_HOST=your-mysql-host
MYSQL_USER=your-mysql-user
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=anime_educational
COHERE_API_KEY=your-cohere-api-key
MASTER_PASSWORD=your-master-password
```

5. Initialize the database:
```bash
python init_db.py
```

## Usage 📱

1. Start the Flask server:
```bash
python app.py
```

2. Access the application through your web browser at `http://localhost:5000`
3. Enter the master password
4. Register or login to your account
5. Start learning through:
   - Chat with AI tutor
   - Take quizzes
   - Track your progress
   - Set learning goals

## Development 🛠️

### Project Structure
```
anime-educational-chatbot/
├── app.py                   # Main application file
├── requirements.txt         # Project dependencies
├── models.py               # Database models
├── init_db.py             # Database initialization
├── create_admin.py        # Admin user creation
├── static/                # Static assets
│   ├── images/           # Image files
│   ├── audio/            # Audio files
│   └── css/              # Stylesheets
├── templates/            # HTML templates
└── uploads/             # User uploads directory
```

### Adding New Features
1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Submit a pull request

## Deployment 🌐

The application can be deployed on any platform that supports Python/Flask applications:

1. Set up a Python environment on your server
2. Install dependencies using `requirements.txt`
3. Configure environment variables
4. Use Gunicorn as the WSGI server:
```bash
gunicorn -c gunicorn_config.py app:app
```

## Contributing 🤝

Contributions are welcome! Please feel free to submit a Pull Request.

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments 🙏

- Cohere for AI capabilities
- Flask for the web framework
- All contributors and users of the application

## Contact 📧

For any questions or support, please open an issue in the GitHub repository.

---
Made by Shubh Rakesh Nahar from Troy University for educational purposes 