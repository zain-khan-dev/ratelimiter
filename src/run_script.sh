#!/bin/bash

source .venv/bin/activate

# Run FastAPI app
uvicorn src.main:app --host 0.0.0.0 --port 8000