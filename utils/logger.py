from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        base: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "time": int(record.created * 1000),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        if hasattr(record, "extra") and isinstance(getattr(record, "extra"), dict):
            base.update(getattr(record, "extra"))
        return json.dumps(base, ensure_ascii=False)


def get_logger(name: str = "linkedin-wrapping-service") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def parse_user_agent(ua: Optional[str]) -> Dict[str, Any]:
    if not ua:
        return {}
    parsed: Dict[str, Any] = {"original": ua}
    try:
        # Prefer the user-agents library if available
        try:
            from user_agents import parse as ua_parse  # type: ignore
        except Exception:  # pragma: no cover - optional dependency
            ua_parse = None  # type: ignore

        if ua_parse:
            ua_obj = ua_parse(ua)
            browser_name = ua_obj.browser.family or "Unknown"
            browser_version = ".".join([v for v in [ua_obj.browser.version_string] if v]) or None
            os_name = ua_obj.os.family or None
            os_version = ua_obj.os.version_string or None
            device_name = ua_obj.device.family or None
            parsed.update({
                "name": browser_name,
                **({"version": browser_version} if browser_version else {}),
                "os": {
                    **({"name": os_name} if os_name else {}),
                    **({"version": os_version} if os_version else {}),
                    **({"full": f"{os_name} {os_version}".strip() if os_name or os_version else None} if (os_name or os_version) else {}),
                },
                "device": {**({"name": device_name} if device_name else {})},
            })
        else:
            # Fallback minimal parsing
            name = None
            version = None
            if "Chrome/" in ua and "Safari/" in ua:
                name = "Chrome"
                try:
                    version = ua.split("Chrome/")[1].split(" ")[0]
                except Exception:
                    version = None
            elif "Safari/" in ua and "Chrome/" not in ua:
                name = "Safari"
            elif "Firefox/" in ua:
                name = "Firefox"
                try:
                    version = ua.split("Firefox/")[1]
                except Exception:
                    version = None
            parsed["name"] = name or "Unknown"
            if version:
                parsed["version"] = version
            if "Mac OS X" in ua:
                parsed["os"] = {"name": "Mac OS X"}
            elif "Windows" in ua:
                parsed["os"] = {"name": "Windows"}
            elif "Linux" in ua:
                parsed["os"] = {"name": "Linux"}
            if "Macintosh" in ua:
                parsed["device"] = {"name": "Mac"}
            elif "Windows" in ua:
                parsed["device"] = {"name": "PC"}
    except Exception:
        # Best-effort parsing only
        pass
    return parsed


def build_log_payload(
    *,
    started_at_ns: int,
    method: str,
    url_path: str,
    url_scheme: Optional[str],
    url_domain: Optional[str],
    origin: Optional[str],
    user_agent: Optional[str],
    authorization: Optional[str],
    client_ip: Optional[str],
    status_code: int,
    response_headers: Dict[str, str],
    destination_geo: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    duration_ms = int((time.time_ns() - started_at_ns) / 1_000_000)
    request_block: Dict[str, Any] = {
        "authorization": authorization,
        "method": method,
        "origin": origin,
        "url": {
            "path": url_path,
            "original": url_path,
            "scheme": url_scheme,
            "domain": url_domain,
        },
        "user_agent": parse_user_agent(user_agent),
    }
    # Only include keys with non-empty values to keep logs tidy
    if not authorization:
        request_block.pop("authorization", None)

    response_block: Dict[str, Any] = {
        "status_code": status_code,
        "time": duration_ms,
    }
    # Surface common CORS headers if present
    for h in [
        "access-control-allow-origin",
        "access-control-allow-credentials",
        "access-control-allow-headers",
        "access-control-allow-methods",
    ]:
        if h in response_headers:
            response_block[h] = response_headers[h]

    destination_block: Dict[str, Any] = {
        "ip": client_ip,
    }
    if destination_geo:
        destination_block["geo"] = destination_geo
    payload: Dict[str, Any] = {
        "request": request_block,
        "response": response_block,
        "destination": destination_block,
    }
    return payload


def _is_private_ip(ip: Optional[str]) -> bool:
    if not ip:
        return True
    try:
        if ip.startswith("127.") or ip == "::1":
            return True
        if ip.startswith("10."):
            return True
        if ip.startswith("192.168."):
            return True
        if ip.startswith("172."):
            # 172.16.0.0 – 172.31.255.255
            try:
                second = int(ip.split(".")[1])
                return 16 <= second <= 31
            except Exception:
                return False
    except Exception:
        return False
    return False


async def lookup_geo(ip: Optional[str]) -> Dict[str, Any]:
    if _is_private_ip(ip):
        return {}
    base = os.getenv("GEO_LOOKUP_BASE", "https://ipwho.is")
    url = f"{base}/{ip}"
    timeout_ms = int(os.getenv("GEO_LOOKUP_TIMEOUT_MS", "150"))
    try:
        import httpx  # local import to keep baseline lightweight
        async with httpx.AsyncClient(timeout=timeout_ms / 1000.0) as client:
            resp = await client.get(url)
            data = resp.json()
            # ipwho.is returns {success: bool, ...}
            if not data or ("success" in data and not data.get("success")):
                return {}
            lat = data.get("latitude")
            lon = data.get("longitude")
            geo = {
                "region_iso_code": data.get("region_code"),
                "continent_name": data.get("continent"),
                "city_name": data.get("city"),
                "country_iso_code": data.get("country_code"),
                "country_name": data.get("country"),
                "location": {"lon": lon, "lat": lat} if lat is not None and lon is not None else None,
                "region_name": data.get("region"),
            }
            # Drop None location if incomplete
            if geo.get("location") is None:
                geo.pop("location", None)
            return geo
    except Exception:
        return {}

