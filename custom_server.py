import os
import uuid
import shutil
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional

import boto3
import httpx
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import MinerU logic
from mineru.cli.common import do_parse

app = FastAPI(title="MinerU Custom URL Parser Wrapper")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database to store task statuses and results
tasks_db: Dict[str, Dict[str, Any]] = {}

class SubmitTaskRequest(BaseModel):
    url: str
    backend: Optional[str] = "pipeline"

def download_file(url: str, dest_path: str):
    parsed = urllib.parse.urlparse(url)
    
    if parsed.scheme == "s3":
        bucket_name = parsed.netloc
        # Remove leading slash from the path to get the S3 Key
        s3_key = parsed.path.lstrip("/")
        
        # Download from S3 using local credentials/role
        s3_client = boto3.client("s3")
        s3_client.download_file(bucket_name, s3_key, dest_path)
        
    elif parsed.scheme in ("http", "https"):
        # Download from HTTP/HTTPS URL
        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(dest_path, "wb") as f:
                f.write(response.content)
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

def parse_worker(task_id: str, url: str, backend: str):
    tasks_db[task_id]["status"] = "processing"
    
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
            
        # 3. Call MinerU parsing engine
        do_parse(
            output_dir=str(output_dir),
            pdf_file_names=["document"],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=["ch"],
            backend=backend,
            parse_method="auto",
            formula_enable=True,
            table_enable=True,
            image_analysis=True,
        )
        
        # 4. Search recursively inside the output directory for the generated .md file
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
        else:
            raise FileNotFoundError("Could not find the generated markdown file in output directory.")
            
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        tasks_db[task_id]["error"] = str(e)
        
    finally:
        # Cleanup temporary files
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            if output_dir.exists():
                shutil.rmtree(output_dir)
        except Exception:
            pass

@app.post("/submit-task", status_code=202)
def submit_task(request: SubmitTaskRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    
    # Store initial task state
    tasks_db[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "url": request.url
    }
    
    # Run the worker in the background
    background_tasks.add_task(parse_worker, task_id, request.url, request.backend)
    
    return {"task_id": task_id}

@app.get("/get-response/{task_id}")
def get_response(task_id: str):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    response = {
        "task_id": task["task_id"],
        "status": task["status"],
    }
    
    if task["status"] == "completed":
        response["markdown"] = task["markdown"]
    elif task["status"] == "failed":
        response["error"] = task.get("error", "Unknown error occurred during parsing")
        
    return response

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
