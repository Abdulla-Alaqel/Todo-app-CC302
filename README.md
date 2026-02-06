# In-Memory Flask To‑Do App

Simple Flask to-do list storing tasks in a global Python list (no database).

Quick start (Linux/macOS):

1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Run the app

```bash
export FLASK_APP=app.py
flask run --reload
```

Open http://127.0.0.1:5000 in your browser.

Docker
------

Build and push to Docker Hub (replace USER/REPO and TAG):

```bash
# Build (from project root)
docker build -t USER/REPO:TAG .

# Log in to Docker Hub
docker login

# Push
docker push USER/REPO:TAG

# Run locally
docker run -p 5000:5000 USER/REPO:TAG
```

Notes:
- Replace `USER/REPO:TAG` with your Docker Hub repo, e.g. `alice/todo-app:latest`.
- If you prefer to test locally without pushing, use `docker build -t todo-app:local .` and `docker run -p 5000:5000 todo-app:local`.
