Here is a complete, minimal proof-of-concept for `rrweb`. It uses an in-memory FastAPI backend to catch the events, an Nginx-served storefront to record them, and an Nginx-served admin panel to replay them.

### Project Structure

Create a new directory and set up the following structure:

```text
rrweb-poc/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── storefront/
│   ├── Dockerfile
│   └── index.html
└── admin/
    ├── Dockerfile
    └── index.html

```

### 1. Root Configuration

**`docker-compose.yml`**

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
  storefront:
    build: ./storefront
    ports:
      - "8080:80"
  admin:
    build: ./admin
    ports:
      - "8081:80"

```

### 2. The FastAPI Backend

This will hold the events in memory for simplicity.

**`backend/requirements.txt`**

```text
fastapi
uvicorn
pydantic

```

**`backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

```

**`backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any

app = FastAPI()

# Allow CORS so the frontend containers can push/pull data
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EventPayload(BaseModel):
    events: List[Dict[str, Any]]

# In-memory session store (will reset if the container restarts)
recorded_events = []

@app.post("/events")
async def receive_events(payload: EventPayload):
    recorded_events.extend(payload.events)
    return {"status": "ok", "total_events": len(recorded_events)}

@app.get("/events")
async def get_events():
    return recorded_events

```

### 3. The Storefront (Recorder)

This simulates a basic apparel shop. It records interactions and flushes them to the backend every 3 seconds.

**`storefront/Dockerfile`**

```dockerfile
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/

```

**`storefront/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Storefront</title>
    <script src="https://cdn.jsdelivr.net/npm/rrweb@latest/dist/rrweb.min.js"></script>
    <style>
        body { font-family: sans-serif; padding: 3rem; background: #fafafa; }
        .card { background: white; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); width: 300px; }
        button { background: #000; color: #fff; border: none; padding: 10px 20px; cursor: pointer; margin-top: 15px;}
        input { padding: 8px; width: 100%; margin-top: 10px; box-sizing: border-box; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Delusions of Grandeur <br><small><i>(*suffering from)</i></small></h1>
        <p>Premium Heavyweight T-Shirt</p>
        <input type="text" placeholder="Enter sizing notes (e.g., L)" />
        <button onclick="alert('Added to cart!')">Add to Cart</button>
    </div>

    <script>
        let events = [];
        
        // Start recording
        rrweb.record({
            emit(event) {
                events.push(event);
            },
        });

        // Batch send to FastAPI every 3 seconds
        setInterval(() => {
            if (events.length > 0) {
                fetch('http://localhost:8000/events', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ events: events }),
                }).catch(err => console.error(err));
                
                events = []; // Clear queue after sending
            }
        }, 3000);
    </script>
</body>
</html>

```

### 4. The Admin Panel (Replayer)

This pulls the global list of events from FastAPI and rebuilds the DOM inside a sandbox to replay the session.

**`admin/Dockerfile`**

```dockerfile
FROM nginx:alpine
COPY index.html /usr/share/nginx/html/

```

**`admin/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Admin - Replay Sessions</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/rrweb@latest/dist/rrweb.min.css" />
    <script src="https://cdn.jsdelivr.net/npm/rrweb@latest/dist/rrweb.min.js"></script>
    <style>
        body { font-family: sans-serif; padding: 2rem; }
        #replay-container { width: 1024px; height: 768px; border: 2px dashed #ccc; margin-top: 1rem; background: #f0f0f0; }
        button { padding: 10px 20px; font-size: 16px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Session Replay Admin</h1>
    <button onclick="loadAndPlay()">Fetch and Play Latest Interactions</button>
    
    <div id="replay-container"></div>

    <script>
        async function loadAndPlay() {
            try {
                const response = await fetch('http://localhost:8000/events');
                const events = await response.json();

                if (events.length < 2) {
                    alert("Not enough data yet. Go click around the storefront first!");
                    return;
                }

                // Clear previous replay if any
                document.getElementById('replay-container').innerHTML = '';

                // Initialize replayer
                const replayer = new rrweb.Replayer(events, {
                    root: document.getElementById('replay-container'),
                });
                
                replayer.play();
            } catch (error) {
                console.error("Error fetching events:", error);
                alert("Make sure the backend is running and you have visited the storefront.");
            }
        }
    </script>
</body>
</html>

```

### How to Run It

1. Open your terminal (from your macOS environment) inside the `rrweb-poc` directory.
2. Spin up the cluster:
```bash
docker compose up --build

```


3. Open **`http://localhost:8080`** in your browser. Move your mouse, type in the input field, and click the button. Wait ~3 seconds for the batch upload to fire.
4. Open **`http://localhost:8081`** in a second tab. Click "Fetch and Play Latest Interactions" to watch your exact cursor movements, typing, and clicks replayed within the dashed container.
