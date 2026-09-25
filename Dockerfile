FROM python:3.10-slim

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Strict environment variables to prevent CPU/RAM thread hogging
ENV OMP_NUM_THREADS=2
ENV MKL_NUM_THREADS=2
ENV OPENBLAS_NUM_THREADS=2
ENV VECLIB_MAXIMUM_THREADS=2
ENV NUMEXPR_NUM_THREADS=2
ENV TOKENIZERS_PARALLELISM=false
ENV MINERU_MODEL_SOURCE=huggingface

WORKDIR /app

# Install system dependencies needed for OpenCV, PDF text extraction, and graphics rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    poppler-utils \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

# Install Python dependencies, CPU-only PyTorch, and local mineru package with pipeline & s3 extras
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -e .[pipeline,s3]

# Download ONLY the lightweight pipeline model weights into container image
RUN mineru-models-download -s huggingface -m pipeline

# Expose server port 8080
EXPOSE 8080

# Run Uvicorn server with 1 worker to guarantee strict single-process queue and RAM limit execution
CMD ["uvicorn", "custom_server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
