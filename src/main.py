from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from .routers import front_page

app = FastAPI()

app.include_router(front_page.router)

