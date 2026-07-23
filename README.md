# Custom OCR Service Server

A lightweight FastAPI-based Custom OCR Server designed for document parsing and OCR requests.

## Features

- **Document Parsing API (`POST /parse`)**: Parse PDF documents and images with standard/high-precision OCR options.
- **Health Check (`GET /health`)**: Server status check.
- **Asynchronous Task API (`POST /tasks`, `GET /tasks/{task_id}`)**: Background asynchronous document processing.

## Running the Server

Start the custom server using Uvicorn:

```bash
python custom_server.py
```

Or run via Uvicorn directly:

```bash
uvicorn custom_server:app --host 0.0.0.0 --port 8000 --reload
```

## API Documentation

Once running, interactive API docs are available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

See [custom_server.md](file:///e:/Karamveer/magic_roll/ocr_service/custom_server.md) for endpoint usage details.
