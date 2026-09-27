import os
import time
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import httpx

logger = logging.getLogger("LexSetu.IndiaCodeClient")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

INDIACODE_API_BASE = os.getenv("INDIACODE_API_BASE", "https://indiacode.ecourtsindia.com/api/v1")
SOURCE_TYPE = "INDIA_CODE_API"
SOURCE_AUTHORITY = "INDIA_CODE_CORPUS"


class IndiaCodeAPIError(Exception):
    """Raised when the India Code API encounters an unrecoverable failure."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class IndiaCodeClient:
    """
    Deterministic client for the India Code Statute API (by eCourtsIndia).
    Preserves exact verbatim source text, raw payloads, and computes SHA-256 hashes.
    Never alters legal text, never fabricates metadata, never uses LLMs.
    """

    def __init__(self, base_url: str = INDIACODE_API_BASE, timeout: float = 3.0, max_retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        parsed = urlparse(self.base_url)
        self.source_api = parsed.netloc or "indiacode.ecourtsindia.com"

    def _request_with_retry(self, method: str, url: str, params: Optional[Dict[str, Any]] = None) -> httpx.Response:
        """
        Executes HTTP requests with exponential backoff for transient network / 5xx errors.
        Never retries on client errors (404, 400).
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                    resp = client.request(method, url, params=params)
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                        sleep_time = 0.5 * (2 ** (attempt - 1))
                        logger.warning(f"Transient HTTP {resp.status_code} for {url}, retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue
                    return resp
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.max_retries:
                    sleep_time = 0.5 * (2 ** (attempt - 1))
                    logger.warning(f"Network error {e} for {url}, retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                raise IndiaCodeAPIError(f"Network error after {self.max_retries} attempts: {e}")

        raise IndiaCodeAPIError(f"HTTP request failed: {last_error}")

    def get_meta(self) -> Dict[str, Any]:
        """
        Fetches /meta endpoint containing corpus counts, build hash, date, and enums.
        """
        url = f"{self.base_url}/meta"
        resp = self._request_with_retry("GET", url)
        if resp.status_code != 200:
            raise IndiaCodeAPIError(f"/meta returned HTTP {resp.status_code}", resp.status_code, resp.text)
        raw_text = resp.text
        raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        data = resp.json()
        return {
            "data": data,
            "raw_text": raw_text,
            "raw_response_sha256": raw_hash,
            "source_api": self.source_api,
            "source_url": url,
        }

    def get_openapi(self) -> Dict[str, Any]:
        """
        Fetches /openapi.json specification.
        """
        url = f"{self.base_url}/openapi.json"
        resp = self._request_with_retry("GET", url)
        if resp.status_code != 200:
            raise IndiaCodeAPIError(f"/openapi.json returned HTTP {resp.status_code}", resp.status_code, resp.text)
        return resp.json()

    def search_acts(self, q: str, jurisdiction: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        """
        Queries /acts endpoint with substring search q.
        """
        url = f"{self.base_url}/acts"
        params: Dict[str, Any] = {"q": q, "limit": limit}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        resp = self._request_with_retry("GET", url, params=params)
        if resp.status_code != 200:
            raise IndiaCodeAPIError(f"/acts query '{q}' returned HTTP {resp.status_code}", resp.status_code, resp.text)
        return resp.json()

    def get_act(self, act_id: str) -> Dict[str, Any]:
        """
        Fetches /acts/{act} which contains Act metadata and provision summary list.
        Notice: this does NOT contain full section text; section text requires get_section().
        """
        clean_id = act_id.strip().lower()
        url = f"{self.base_url}/acts/{clean_id}"
        resp = self._request_with_retry("GET", url)
        if resp.status_code == 404:
            raise IndiaCodeAPIError(f"Act '{clean_id}' not found on source API", 404, resp.text)
        if resp.status_code != 200:
            raise IndiaCodeAPIError(f"Act '{clean_id}' returned HTTP {resp.status_code}", resp.status_code, resp.text)
        
        raw_text = resp.text
        raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        data = resp.json()
        
        # Calculate content hash based on act core metadata
        act_info = data.get("act", {})
        content_repr = f"{act_info.get('id')}:{act_info.get('short_title')}:{act_info.get('act_year')}:{act_info.get('act_number')}"
        content_hash = hashlib.sha256(content_repr.encode("utf-8")).hexdigest()

        return {
            "data": data,
            "raw_text": raw_text,
            "raw_response_sha256": raw_hash,
            "content_sha256": content_hash,
            "source_api": self.source_api,
            "source_url": act_info.get("url") or url,
        }

    def get_section(self, act_id: str, provision_number: str) -> Dict[str, Any]:
        """
        Fetches /{act}/section/{number} containing verbatim section text, HTML, and attachments.
        provision_number is preserved strictly as a string.
        """
        clean_act = act_id.strip().lower()
        clean_num = str(provision_number).strip()
        url = f"{self.base_url}/{clean_act}/section/{clean_num}"
        resp = self._request_with_retry("GET", url)
        if resp.status_code == 404:
            raise IndiaCodeAPIError(f"Section '{clean_num}' of '{clean_act}' not found on source API", 404, resp.text)
        if resp.status_code != 200:
            raise IndiaCodeAPIError(f"Section '{clean_num}' of '{clean_act}' returned HTTP {resp.status_code}", resp.status_code, resp.text)

        raw_text = resp.text
        raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        data = resp.json()

        # Extract exact verbatim text from section sub-object
        section_obj = data.get("section", {})
        verbatim_text = section_obj.get("text")
        
        # Dual hashing: content_sha256 hashes the verbatim text itself
        text_for_hash = (verbatim_text or "").strip().encode("utf-8")
        content_hash = hashlib.sha256(text_for_hash).hexdigest() if verbatim_text is not None else None

        return {
            "data": data,
            "raw_text": raw_text,
            "raw_response_sha256": raw_hash,
            "content_sha256": content_hash,
            "source_api": self.source_api,
            "source_url": data.get("url") or url,
        }

    def get_all_mappings(self, pair: Optional[str] = None, from_act: Optional[str] = None, page_limit: int = 100) -> List[Dict[str, Any]]:
        """
        Paginates through /mappings strictly following the returned 'next' URL until next is null.
        Never reconstructs or assumes offset += limit.
        """
        results: List[Dict[str, Any]] = []
        next_url: Optional[str] = f"{self.base_url}/mappings"
        params: Optional[Dict[str, Any]] = {"limit": page_limit}
        if pair:
            params["pair"] = pair
        elif from_act:
            params["from"] = from_act

        while next_url:
            resp = self._request_with_retry("GET", next_url, params=params)
            # After first request, params are already encoded in next_url
            params = None

            if resp.status_code != 200:
                logger.error(f"Mappings pagination failed at {next_url}: HTTP {resp.status_code}")
                raise IndiaCodeAPIError(f"Mappings request failed: HTTP {resp.status_code}", resp.status_code, resp.text)

            page_data = resp.json()
            mappings_batch = page_data.get("mappings", [])
            for item in mappings_batch:
                # Capture raw JSON representation per mapping for auditability
                item["_raw_json"] = json.dumps(item, ensure_ascii=False)
                results.append(item)

            next_url = page_data.get("next")
            if next_url:
                logger.debug(f"Following next mapping page: {next_url}")

        return results
