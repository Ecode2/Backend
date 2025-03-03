# BookVerse Backend

## Overview
BookVerse is an online book reader platform with automated audio reading capabilities, allowing users to read and listen to books conveniently. This repository contains the backend implementation, built with Django, a high-level Python web framework. The backend handles user authentication, book management, audio generation, and API endpoints for the frontend.

## Features
- User authentication and authorization (login, signup, roles).
- Book management (upload, store, retrieve books in various formats).
- Automated audio generation for books using text-to-speech (TTS) APIs or libraries.
- RESTful API endpoints for seamless frontend integration.
- Database management for user data, books, and audio files.

## Technologies
- **Python**: 3.11+
- **Django**: 4.2+
- **Django REST Framework**: For building APIs
- **PostgreSQL** or **SQLite**: For database storage (configurable)
- **Text-to-Speech Libraries**: e.g., `gTTS` (Google Text-to-Speech) or `pyttsx3` for audio generation

## Prerequisites
- Python 3.11 or higher
- Pip (Python package manager)
- PostgreSQL or SQLite (for development, SQLite is recommended for simplicity)
- Virtual environment tool (e.g., `venv` or `virtualenv`)

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/Ecode2/backend.git
cd bookverse-backend

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory with the following variables:
```
SECRET_KEY=your-django-secret-key
DEBUG=True  # Set to False for production
DATABASE_URL=postgresql://user:password@localhost:5432/bookverse  # Or use SQLite for development
```

### 5. Apply Migrations
```bash
python manage.py migrate
```

### 6. Run the Development Server
```bash
python manage.py runserver
```

The backend will be available at `http://localhost:8000`.

### 7. API Endpoints
- `/api/auth/login/`: User login
- `/api/auth/signup/`: User registration
- `/api/books/`: List and create books
- `/api/books/{id}/audio/`: Generate or retrieve audio for a book
- Refer to the `docs/` directory for detailed Swagger/OpenAPI documentation (if implemented).


## Deployment
- For production, configure environment variables with `DEBUG=False`, use a WSGI server like Gunicorn, and deploy with Nginx or a similar reverse proxy.

## Contributing
1. Fork the repository.
2. Create a branch for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add your feature description"
   ```
4. Push to the branch:
   ```bash
   git push origin feature/your-feature
   ```
5. Submit a pull request.

## Contact
For questions or support, contact us at [ecode5814@gmail.com](mailto:ecode5814@gmail.com).
