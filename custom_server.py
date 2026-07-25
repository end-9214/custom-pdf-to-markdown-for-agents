import os
# Configure strict thread limits before importing torch/numpy to prevent RAM/CPU hogging
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["VECLIB_MAXIMUM_THREADS"] = "2"
os.environ["NUMEXPR_NUM_THREADS"] = "2"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import asyncio
import gc
import shutil
import time
import urllib.parse
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional

import boto3
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import MinerU logic
from mineru.cli.common import do_parse

try:
    import torch
    # Restrict PyTorch cpu threads to prevent CPU/RAM spike
    torch.set_num_threads(2)
except ImportError:
    torch = None

# In-memory database to store task statuses and results
tasks_db: Dict[str, Dict[str, Any]] = {}
task_queue: asyncio.Queue = asyncio.Queue()
current_active_task: Optional[str] = None
processed_counter: int = 0

def cleanup_system_memory():
    """Aggressive memory release helper."""
    gc.collect()
    if torch:
        if torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            except Exception:
                pass

async def queue_worker():
    """Background worker loop that processes tasks from the queue strictly 1 by 1."""
    global current_active_task, processed_counter
    while True:
        task_id = await task_queue.get()
        current_active_task = task_id
        try:
            task_info = tasks_db.get(task_id)
            if task_info and task_info["status"] == "pending":
                # Execute parse synchronously in threadpool to prevent blocking the async event loop
                await asyncio.to_thread(
                    execute_parse_job,
                    task_id=task_id,
                    url=task_info["url"],
                    backend="pipeline", # Always enforce lightweight pipeline backend
                    formula_enable=task_info.get("formula_enable", True),
                    table_enable=task_info.get("table_enable", True),
                )
                processed_counter += 1
        except Exception as e:
            if task_id in tasks_db:
                tasks_db[task_id]["status"] = "failed"
                tasks_db[task_id]["error"] = f"Queue worker unexpected exception: {str(e)}"
        finally:
            current_active_task = None
            task_queue.task_done()
            cleanup_system_memory()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the worker task on startup
    worker_task = asyncio.create_task(queue_worker())
    yield
    # Cancel worker task on shutdown
    worker_task.cancel()

app = FastAPI(title="MinerU Lightweight Sequential PDF Parser Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SubmitTaskRequest(BaseModel):
    url: str
    formula_enable: Optional[bool] = True
    table_enable: Optional[bool] = True

def download_file(url: str, dest_path: str):
    parsed = urllib.parse.urlparse(url)
    
    if parsed.scheme == "s3":
        bucket_name = parsed.netloc
        s3_key = parsed.path.lstrip("/")
        s3_client = boto3.client("s3")
        s3_client.download_file(bucket_name, s3_key, dest_path)
    elif parsed.scheme in ("http", "https"):
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

def execute_parse_job(task_id: str, url: str, backend: str = "pipeline", formula_enable: bool = True, table_enable: bool = True):
    tasks_db[task_id]["status"] = "processing"
    tasks_db[task_id]["started_at"] = time.time()
    
    temp_dir = Path(f"./temp_{task_id}")
    output_dir = Path(f"./output_{task_id}")
    
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Download the PDF file
        local_pdf_path = temp_dir / "document.pdf"
        download_file(url, str(local_pdf_path))
        
        # 2. Read the file bytes
        with open(local_pdf_path, "rb") as f:
            pdf_bytes = f.read()
            
        # 3. Call MinerU parsing engine with lightweight pipeline backend
        do_parse(
            output_dir=str(output_dir),
            pdf_file_names=["document"],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=["ch"],
            backend="pipeline", # Strict lightweight pipeline backend
            parse_method="auto",
            formula_enable=formula_enable,
            table_enable=table_enable,
            image_analysis=True,
            f_draw_layout_bbox=False, # Disable extra debug drawings to save RAM and disk
            f_draw_span_bbox=False,
        )
        
        # 4. Search recursively inside output directory for generated .md file
        md_file_path = None
        for path in output_dir.rglob("*.md"):
            if path.is_file():
                md_file_path = path
                break
                
        if md_file_path and md_file_path.exists():
            with open(md_file_path, "r", encoding="utf-8") as f:
                markdown_content = f.read()
            tasks_db[task_id]["status"] = "completed"
            tasks_db[task_id]["markdown"] = markdown_content
            tasks_db[task_id]["completed_at"] = time.time()
        else:
            raise FileNotFoundError("Could not find generated markdown file in output directory.")
            
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        tasks_db[task_id]["error"] = str(e)
        tasks_db[task_id]["failed_at"] = time.time()
        
    finally:
        # Cleanup temporary files safely
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)

@app.post("/submit-task", status_code=202)
async def submit_task(request: SubmitTaskRequest):
    task_id = str(uuid.uuid4())
    created_time = time.time()
    
    # Store task state
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "url": request.url,
        "formula_enable": request.formula_enable,
        "table_enable": request.table_enable,
        "created_at": created_time
    }
    
    # Add task to queue
    await task_queue.put(task_id)
    
    queue_position = task_queue.qsize()
    return {
        "task_id": task_id,
        "status": "pending",
        "queue_position": queue_position
    }

@app.get("/get-response/{task_id}")
def get_response(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    response = {
        "task_id": task["task_id"],
        "status": task["status"],
        "created_at": task.get("created_at"),
    }
    
    if task["status"] == "pending":
        pending_list = [t_id for t_id in list(task_queue._queue) if t_id in tasks_db]
        if task_id in pending_list:
            response["queue_position"] = pending_list.index(task_id) + 1
        else:
            response["queue_position"] = 1
    elif task["status"] == "processing":
        response["started_at"] = task.get("started_at")
    elif task["status"] == "completed":
        response["markdown"] = task.get("markdown")
        response["completed_at"] = task.get("completed_at")
    elif task["status"] == "failed":
        response["error"] = task.get("error", "Unknown error occurred during parsing")
        response["failed_at"] = task.get("failed_at")
        
    return response

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "mode": "pipeline-lightweight",
        "queue_size": task_queue.qsize(),
        "active_task_id": current_active_task,
        "processed_tasks_count": processed_counter,
        "total_tasks_in_db": len(tasks_db)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
