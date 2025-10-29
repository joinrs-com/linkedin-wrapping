import os
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from starlette.middleware.cors import CORSMiddleware

from api.wrapping.router import router as wrapping_router
from utils.logger import get_logger, build_log_payload, lookup_geo
import time


# Load environment variables from local .env if present
_dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_dotenv_path):
    load_dotenv(_dotenv_path)


app = FastAPI(
    title="LinkedIn Wrapping Service",
    description="Service for providing job posting data for LinkedIn wrapping",
    servers=[{
        'url': 'http://linkedin-wrapping-service:3000',
        'description': 'LinkedIn Wrapping Service'
    }]
)

app.include_router(wrapping_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://nextjs-pbox.joinrs.com",
        "https://nextjs-jbox.joinrs.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    stacktrace = traceback.format_exc()
    print(f"Unhandled exception: {exc}")
    print(f"Stacktrace: {stacktrace}")
    return Response(content=f"Unhandled exception: {exc}", status_code=500)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger = get_logger()
    started_at_ns = time.time_ns()
    try:
        response = await call_next(request)
    except Exception:
        # Let exception handler decide the output, but still log attempt
        raise
    try:
        authorization = request.headers.get("authorization")
        origin = request.headers.get("origin")
        user_agent = request.headers.get("user-agent")
        # Extract client IP considering reverse proxies
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
        # Optional geo lookup (non-blocking with small timeout)
        destination_geo = await lookup_geo(client_ip)
        # starlette Headers are case-insensitive; convert to lower-case keys
        response_headers = {k.lower(): v for k, v in response.headers.items()}
        payload = build_log_payload(
            started_at_ns=started_at_ns,
            method=request.method,
            url_path=request.url.path,
            url_scheme=request.url.scheme,
            url_domain=request.url.hostname,
            origin=origin,
            user_agent=user_agent,
            authorization=authorization,
            client_ip=client_ip,
            status_code=response.status_code,
            response_headers=response_headers,
            destination_geo=destination_geo if destination_geo else None,
        )
        logger.info("http_request", extra={"extra": payload})
    except Exception:
        # Never break the request due to logging failures
        pass
    return response


@app.get("/health")
def health():
    return {"Ok!"}


@app.get("/")
def root():
    return {"message": "LinkedIn Wrapping Service API", "version": "1.0.0"}

