# Custom FastAPI Server with S3 PDF Downloading and Parsing

We will build a custom FastAPI server (`custom_server.py`) that acts as a wrapper around the MinerU codebase. It will expose two endpoints:
1. `POST /submit-task`: Accepts a PDF URL (S3 `s3://...` or HTTP `http(s)://...`), downloads the PDF, schedules a background task to parse it using MinerU, and immediately returns a `task_id`.
2. `GET /get-response/{task_id}`: Returns the status (`pending`, `processing`, `completed`, `failed`) and the markdown result once processing is finished.

## Proposed Changes

### [NEW] [custom_server.py](file:///e:/Karamveer/magic_roll/ocr_service/custom_server.py)
We will create a new Python script implementing:
- **FastAPI Application**: Standard FastAPI setup with CORS middleware.
- **S3 / HTTP Downloader**: Integration with `boto3` for S3 downloads and `httpx` for HTTP downloads.
- **Background Worker**: Utilizing FastAPI's `BackgroundTasks` to execute the MinerU `do_parse` function asynchronously.
- **In-Memory Task Store**: A simple thread-safe dictionary to keep track of task statuses and results (markdown data).
- **Execution Script**: Running the server on port `8080`.

## Verification Plan

### Automated / Manual Verification
1. Run the custom server:
   ```powershell
   .\venv\Scripts\python.exe custom_server.py
   ```
2. Submit a task using an HTTP PDF URL:
   ```bash
   curl -X POST "http://127.0.0.1:8080/submit-task" -H "Content-Type: application/json" -d '{"url": "https://arxiv.org/pdf/2409.18839"}'
   ```
3. Poll the status until completed:
   ```bash
   curl "http://127.0.0.1:8080/get-response/<task_id>"
   ```
