import os
import httpx

INDIACODE_API_BASE = os.getenv("INDIACODE_API_BASE", "https://indiacode.ecourtsindia.com/api/v1")


def search_acts(query: str, limit: int = 5) -> list:
    try:
        resp = httpx.get(f"{INDIACODE_API_BASE}/search", params={"q": query, "limit": limit}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])[:limit]
    except Exception as e:
        print(f"[StatuteLookup] search_acts failed: {e}")
        return []


def get_section(act_slug: str, section_number: str) -> dict:
    try:
        resp = httpx.get(f"{INDIACODE_API_BASE}/{act_slug}/section/{section_number}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {
            "act": data.get("act", {}).get("short_title", ""),
            "act_slug": act_slug,
            "section_number": data.get("section", {}).get("number", section_number),
            "heading": data.get("section", {}).get("heading", ""),
            "text": data.get("section", {}).get("text", ""),
            "in_force": data.get("act", {}).get("in_force"),
        }
    except Exception as e:
        print(f"[StatuteLookup] get_section failed for {act_slug}/section/{section_number}: {e}")
        return {}
