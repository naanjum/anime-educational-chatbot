# Anime Educational Chatbot

An AI-powered educational chatbot designed to make learning more engaging by utilizing anime characters and interactive features.

## Features

-   **AI-Powered Chat:** Interact with an AI chatbot persona based on anime characters.
-   **PDF Analysis:** Process and extract information from PDF documents.
-   **Voice Interaction:** Engage with the chatbot using voice input and receive spoken responses.
-   **Personalized Learning:** Potentially offers personalized learning paths (based on previous mentions).
-   **Database Integration:** Utilizes a database for storing information.
-   **Web Interface:** User-friendly interface built with Flask.

## Technologies Used

-   Flask
-   Python (with libraries like `transformers`, `cohere`, `pytesseract`, `pdf2image`, `PyPDF2`, `pdfminer.six`, `pydub`, `gtts`, `google-cloud-texttospeech`, `google-cloud-translate`, `tiktoken`, etc.)
-   Gunicorn (for production server)
-   Docker
-   Fly.io (for deployment)
-   MySQL (or other database)

## Setup and Local Development

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/Skrutz-Z/anime-educational-chatbot.git
    cd anime-educational-chatbot
    ```

2.  **Create a virtual environment:**

    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**

    -   On Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    -   On macOS and Linux:
        ```bash
        source venv/bin/activate
        ```

4.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

5.  **Database Setup:**
    -   Set up your MySQL (or chosen database) and update the connection details in your application configuration (e.g., in `app.py` or a separate config file).
    -   Run database migrations if applicable (e.g., using Flask-Migrate).
    -   You might need to run `init_db.py` or similar scripts to initialize the database.

6.  **API Keys:**
    -   Obtain necessary API keys (e.g., for Cohere, Google Cloud services). Store them securely, preferably using environment variables.

7.  **Run the application:**

    ```bash
    flask run
    ```
    (Or use Gunicorn for testing the production setup locally):
    ```bash
    gunicorn --bind 0.0.0.0:8080 app:app
    ```

## Deployment

The application is configured for deployment on Fly.io using Docker and Gunicorn. The `Dockerfile` and `fly.toml` files are included for this purpose.

Further deployment steps involve building the Docker image and deploying to Fly.io using the `flyctl` CLI.

## Project Structure (Partial)

```
.
├── app.py
├── requirements.txt
├── Dockerfile
├── fly.toml
├── gunicorn_config.py
├── static/
├── templates/
├── migrations/ (if using Flask-Migrate)
├── instance/ (if using instance folder)
├── Keys/ (for storing keys - ensure this is in .gitignore)
├── models.py
├── database_access.md
├── test_db.py
├── create_admin.py
├── init_db.py
└── ... other project files
```

 ## By 
 ##1.Shubh Rakesh Nahar
 ##2. Nafisha Anjum
 ##From Troy University




