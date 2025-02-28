from fastapi import APIRouter, Request
from starlette.responses import Response

from src.decorators.rate_limitter import rate_limit
from src.services.RateLimitStoreService import GranularityLevel

router = APIRouter()


@router.get("/")
@rate_limit(GranularityLevel.MINUTELY, 1, 10)
async def front_page(request: Request, response: Response):
    return {"hello": "worldediting"}


