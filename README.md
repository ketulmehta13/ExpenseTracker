# Full-Stack Expense Tracker

A modern, full-stack expense tracker application featuring a Django REST Framework backend and a React (Vite) frontend styled with Tailwind CSS v4.

## Features
- JWT Authentication (djangorestframework-simplejwt)
- Dashboard with Monthly Trends (Bar Chart) and Expense Breakdown (Pie Chart) using Chart.js
- CRUD Operations for Transactions (Income / Expense)
- Dark Mode support & Modern Aesthetic styling via Tailwind.

---

## Local Development Setup

### Backend (Django)
1. **Navigate to the backend directory**: `cd backend`
2. **Setup virtual environment**: `python -m venv venv` and activate it (e.g. `venv\Scripts\activate` on Windows)
3. **Install dependencies**: `pip install -r requirements.txt` (or install manually: `pip install django djangorestframework djangorestframework-simplejwt django-cors-headers python-dotenv`)
4. **Apply Migrations**: `python manage.py migrate`
5. **Run Server**: `python manage.py runserver`
Backend will run at `http://127.0.0.1:8000/`.

### Frontend (React/Vite)
1. **Navigate to the frontend directory**: `cd frontend`
2. **Install dependencies**: `npm install`
3. **Run Dev Server**: `npm run dev`
Frontend will run locally (typically `http://localhost:5173/`).

---

## Deployment Steps

### Backend Hosting (Render / Railway)
1. Convert your database to PostgreSQL if moving to production (`python-dotenv` and `dj-database-url` are recommended). Add your `DATABASE_URL`.
2. Push your `backend` code repository to GitHub.
3. On Render/Railway, link the GitHub repository.
4. Set Build Command: `pip install -r requirements.txt && python manage.py migrate`
5. Set Start Command: `gunicorn backend_config.wsgi:application`
6. Important Environment Variables:
   - `SECRET_KEY`: Django secret key
   - `DEBUG`: `False`
   - `CORS_ALLOWED_ORIGINS`: Add your Vercel frontend URL.

### Frontend Hosting (Vercel)
1. Ensure your `frontend` code is in a repository.
2. Link the repository to your Vercel account.
3. Vercel automatically detects the Vite framework setting Build Command: `npm run build` & Output Dir: `dist`.
4. Add the Environment Variable `VITE_API_URL` and point it to your deployed Render/Railway backend URL (e.g., `https://your-backend.onrender.com/api`).
5. Deploy.

---

## API Documentation

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/api/auth/register/` | POST | Register new user (`username`, `email`, `password`) | No |
| `/api/auth/login/` | POST | Obtain JWT tokens (`username`, `password`) | No |
| `/api/auth/token/refresh/` | POST | Automatically refreshes simplejwt token | No |
| `/api/auth/me/` | GET | Validates / Retrieves user info | Yes |
| `/api/categories/` | GET, POST | Retrieve or create categories | Yes |
| `/api/transactions/` | GET, POST, PUT, DELETE | CRUD operations and filters on transactions | Yes |

*Note: The frontend Axios interceptor automatically manages `Bearer <token>` attachments to authorized routes.*
