# Custom OCR Service Server (Production 1-by-1 Queue)

A production-ready FastAPI custom wrapper around MinerU designed for high-reliability PDF parsing into Markdown. 

It guarantees **strict 1-PDF-at-a-time sequential execution** via an internal FIFO `asyncio.Queue` worker, ensuring zero resource contention, zero OOM lockups, and clean error isolation across all jobs.

---

## 🚀 One-Command Docker Deployment (Port 8080)

### Option A: Using Docker Run
```bash
docker build -t mineru-ocr-service . && docker run -d -p 8080:8080 --name mineru-ocr-service mineru-ocr-service
```

### Option B: Using Docker Compose
```bash
docker compose up -d --build
```

---

## 💻 Local Development

```bash
python custom_server.py
```
The server will start on `http://0.0.0.0:8080`.

---

## 📡 API Endpoints

### 1. Submit PDF Task
**`POST /submit-task`**
- Enqueues a PDF for conversion. Supports both HTTP(S) and S3 URLs (`s3://bucket/key.pdf`).

**Request:**
```json
{
  "url": "https://arxiv.org/pdf/2409.18839",
  "backend": "pipeline"
}
```

**Response (202 Accepted):**
```json
{
  "task_id": "a1b2c3d4-5678-90ef-1234-56789abcdef0",
  "status": "pending",
  "queue_position": 1
}
```

---

### 2. Poll Task Result
**`GET /get-response/{task_id}`**

**Response (Completed):**
```json
{
  "task_id": "a1b2c3d4-5678-90ef-1234-56789abcdef0",
  "status": "completed",
  "created_at": 1721900000.0,
  "markdown": "# Document Title\n\nParsed content..."
}
```

**Response (Failed - with full error isolation):**
```json
{
  "task_id": "a1b2c3d4-5678-90ef-1234-56789abcdef0",
  "status": "failed",
  "error": "Error details..."
}
```

---

### 3. Server & Queue Health
**`GET /health`**

**Response (200 OK):**
```json
{
  "status": "healthy",
  "queue_size": 0,
  "active_task_id": null,
  "processed_tasks_count": 5,
  "total_tasks_in_db": 5
}
```
