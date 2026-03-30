from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ProBooksAi", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ProBooksAi</title>
  <style>
    body { font-family: sans-serif; max-width: 640px; margin: 60px auto; padding: 0 1rem; }
    h1 { color: #2c3e50; }
    ul { line-height: 2; }
    a { color: #2980b9; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <h1>ProBooksAi 🚀</h1>
  <p>AI-powered accounting software — local dev server is running.</p>
  <ul>
    <li><a href="/health">/health</a> — service health check</li>
    <li><a href="/docs">/docs</a> — interactive API documentation (Swagger UI)</li>
    <li><a href="/redoc">/redoc</a> — alternative API docs (ReDoc)</li>
  </ul>
</body>
</html>"""


@app.get("/health")
def health():
    return {"status": "ok"}
