from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="ProBooksAi")

_HOME_HTML = """\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ProBooksAi</title>
    <style>
      body { font-family: sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; }
      h1   { color: #2c3e50; }
      a    { color: #2980b9; }
      ul   { line-height: 2; }
    </style>
  </head>
  <body>
    <h1>ProBooksAi 🚀</h1>
    <p>Local development server is running.</p>
    <ul>
      <li><a href="/health">/health</a> – service health check</li>
      <li><a href="/docs">/docs</a> – interactive API documentation</li>
    </ul>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home():
    return _HOME_HTML


@app.get("/health")
def health():
    return {"status": "ok"}
