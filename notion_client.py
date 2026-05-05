import json
import os
import re
from urllib import parse, request
from urllib.error import HTTPError, URLError

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION_DEFAULT = "2022-06-28"
NOTION_VERSION_DATA_SOURCES = "2025-09-03"
DEFAULT_MAX_RESULTS = 5
DEFAULT_MAX_PREVIEW_BLOCKS = 3


def get_notion_token():
    return os.getenv("NOTION_TOKEN", "").strip()


def get_notion_page_id():
    return normalize_notion_id(os.getenv("NOTION_PAGE_ID", ""))


def get_notion_target_title():
    return os.getenv("NOTION_TARGET_TITLE", "").strip()


def get_notion_execution_page_id():
    return normalize_notion_id(os.getenv("NOTION_EXECUTION_PAGE_ID", ""))


def get_notion_overview_page_id():
    return normalize_notion_id(os.getenv("NOTION_OVERVIEW_PAGE_ID", ""))


def get_notion_task_database_id():
    return normalize_notion_id(os.getenv("NOTION_TASK_DATABASE_ID", ""))


def get_notion_max_results():
    raw_value = os.getenv("NOTION_MAX_RESULTS", str(DEFAULT_MAX_RESULTS)).strip()
    try:
        return max(1, min(int(raw_value), 10))
    except ValueError:
        return DEFAULT_MAX_RESULTS


def normalize_notion_id(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return ""

    clean_value = raw_value.replace("-", "")
    match = re.search(r"([0-9a-fA-F]{32})", clean_value)
    if not match:
        return ""

    hex_value = match.group(1).lower()
    return (
        f"{hex_value[0:8]}-{hex_value[8:12]}-{hex_value[12:16]}-"
        f"{hex_value[16:20]}-{hex_value[20:32]}"
    )


def notion_request(method, path, payload=None, notion_version=NOTION_VERSION_DEFAULT, query_params=None):
    token = get_notion_token()
    if not token:
        raise ValueError("NOTION_TOKEN belum diatur")

    body = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    url = f"{NOTION_API_BASE}{path}"
    if query_params:
        url = f"{url}?{parse.urlencode(query_params, doseq=True)}"

    req = request.Request(
        url=url,
        data=body,
        headers=headers,
        method=method,
    )
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_title(obj):
    if obj.get("object") == "page":
        properties = obj.get("properties", {})
        for prop in properties.values():
            if prop.get("type") == "title":
                return "".join(item.get("plain_text", "") for item in prop.get("title", [])).strip()
        return "Untitled page"

    if obj.get("object") == "database":
        title = "".join(item.get("plain_text", "") for item in obj.get("title", [])).strip()
        return title or "Untitled database"

    if obj.get("object") == "data_source":
        return obj.get("name", "").strip() or "Untitled data source"

    return "Untitled"


def normalize_search_results(results):
    normalized = []
    for item in results:
        normalized.append(
            {
                "id": item.get("id", ""),
                "object": item.get("object", "unknown"),
                "title": extract_title(item),
                "url": item.get("url", ""),
                "last_edited_time": item.get("last_edited_time", ""),
            }
        )
    return normalized


def select_primary_result(results, target_title):
    if not results:
        return None

    if target_title:
        target_lower = target_title.lower()
        for item in results:
            if item["title"].lower() == target_lower:
                return item
        for item in results:
            if target_lower in item["title"].lower():
                return item

    return results[0]


def fetch_search_results():
    payload = {
        "page_size": get_notion_max_results(),
        "sort": {
            "direction": "descending",
            "timestamp": "last_edited_time",
        },
    }
    target_title = get_notion_target_title()
    if target_title:
        payload["query"] = target_title

    response = notion_request("POST", "/search", payload)
    return normalize_search_results(response.get("results", []))


def fetch_page(page_id):
    response = notion_request("GET", f"/pages/{page_id}")
    return {
        "id": response.get("id", page_id),
        "object": response.get("object", "page"),
        "title": extract_title(response),
        "url": response.get("url", ""),
        "last_edited_time": response.get("last_edited_time", ""),
    }


def extract_rich_text(block):
    block_type = block.get("type")
    if not block_type:
        return ""

    if block_type == "child_database":
        return block.get("child_database", {}).get("title", "").strip()

    if block_type == "child_page":
        return block.get("child_page", {}).get("title", "").strip()

    type_data = block.get(block_type, {})
    rich_text = type_data.get("rich_text", [])
    return "".join(item.get("plain_text", "") for item in rich_text).strip()


def fetch_page_preview(page_id, max_blocks=DEFAULT_MAX_PREVIEW_BLOCKS):
    response = notion_request("GET", f"/blocks/{page_id}/children", query_params={"page_size": 20})
    preview_lines = []

    for block in response.get("results", []):
        text = extract_rich_text(block)
        if not text:
            continue

        preview_lines.append(text)
        if len(preview_lines) >= max_blocks:
            break

    return preview_lines


def parse_date_value(property_value):
    date_value = property_value.get("date")
    if not date_value:
        return ""
    return date_value.get("start") or ""


def parse_multi_select_names(property_value):
    return [item.get("name", "").strip() for item in property_value.get("multi_select", []) if item.get("name")]


def parse_title_property(property_value):
    return "".join(item.get("plain_text", "") for item in property_value.get("title", [])).strip()


def parse_select_name(property_value):
    select_value = property_value.get("select")
    return (select_value or {}).get("name", "").strip()


def parse_status_name(property_value):
    status_value = property_value.get("status")
    return (status_value or {}).get("name", "").strip()


def parse_number_value(property_value):
    value = property_value.get("number")
    return value if value is not None else None


def parse_relation_value(property_value):
    return [item.get("id", "") for item in property_value.get("relation", []) if item.get("id")]


def extract_task_from_page(page):
    properties = page.get("properties", {})
    return {
        "id": page.get("id", ""),
        "url": page.get("url", ""),
        "name": parse_title_property(properties.get("Name", {})) or "Untitled task",
        "status": parse_status_name(properties.get("Status", {})),
        "priority": parse_select_name(properties.get("Priority", {})),
        "time_horizon": parse_select_name(properties.get("Time Horizon", {})),
        "date": parse_date_value(properties.get("Date", {})),
        "category": parse_multi_select_names(properties.get("Category", {})),
        "module": parse_multi_select_names(properties.get("Module", {})),
        "points": parse_number_value(properties.get("Points", {})),
        "project_relation_ids": parse_relation_value(properties.get("Project", {})),
    }


def build_daily_task_filter():
    return {
        "and": [
            {
                "property": "Time Horizon",
                "select": {
                    "equals": "Daily",
                },
            },
            {
                "property": "Status",
                "status": {
                    "does_not_equal": "Done",
                },
            },
        ]
    }


def build_daily_task_sorts():
    return [
        {
            "property": "Date",
            "direction": "ascending",
        },
        {
            "property": "Priority",
            "direction": "ascending",
        },
    ]


def fetch_task_items():
    data_source_id = get_notion_task_database_id()
    if not data_source_id:
        return {
            "status": "unavailable",
            "summary": "NOTION_TASK_DATABASE_ID belum diatur",
            "tasks": [],
        }

    payload = {
        "page_size": 10,
        "result_type": "page",
        "filter": build_daily_task_filter(),
        "sorts": build_daily_task_sorts(),
    }
    query_params = {
        "filter_properties": [
            "Name",
            "Status",
            "Priority",
            "Time Horizon",
            "Date",
            "Category",
            "Module",
            "Points",
            "Project",
        ]
    }
    response = notion_request(
        "POST",
        f"/data_sources/{data_source_id}/query",
        payload=payload,
        notion_version=NOTION_VERSION_DATA_SOURCES,
        query_params=query_params,
    )
    tasks = [extract_task_from_page(item) for item in response.get("results", []) if item.get("object") == "page"]

    if not tasks:
        return {
            "status": "ok",
            "summary": "tidak ada daily task yang belum selesai",
            "tasks": [],
        }

    return {
        "status": "ok",
        "summary": f"{len(tasks)} daily task aktif",
        "tasks": tasks,
    }


def fetch_notion_snapshot():
    if not get_notion_token():
        return {
            "status": "unavailable",
            "summary": "NOTION_TOKEN belum diatur",
            "primary": None,
            "preview_lines": [],
            "resources": [],
            "anchors": {},
            "task_snapshot": {
                "status": "unavailable",
                "summary": "NOTION_TOKEN belum diatur",
                "tasks": [],
            },
        }

    try:
        resources = fetch_search_results()

        execution_page_id = get_notion_execution_page_id() or get_notion_page_id()
        overview_page_id = get_notion_overview_page_id()
        primary_page_id = execution_page_id or get_notion_page_id()

        primary = fetch_page(primary_page_id) if primary_page_id else None
        if not primary:
            primary = select_primary_result(resources, get_notion_target_title())

        preview_lines = []
        if primary and primary["object"] == "page":
            preview_lines = fetch_page_preview(primary["id"])

        anchors = {
            "execution": fetch_page(execution_page_id) if execution_page_id else None,
            "overview": fetch_page(overview_page_id) if overview_page_id else None,
        }
        task_snapshot = fetch_task_items()

        summary_parts = []
        if task_snapshot["status"] == "ok":
            summary_parts.append(task_snapshot["summary"])
        else:
            summary_parts.append(f"daily task unavailable: {task_snapshot['summary']}")

        if resources:
            summary_parts.append(f"{len(resources)} resource Notion accessible")

        return {
            "status": "ok",
            "summary": "; ".join(summary_parts) if summary_parts else "Notion connected",
            "primary": primary,
            "preview_lines": preview_lines,
            "resources": resources,
            "anchors": anchors,
            "task_snapshot": task_snapshot,
        }
    except HTTPError as error:
        try:
            error_body = error.read().decode("utf-8")
        except Exception:
            error_body = ""
        return {
            "status": "unavailable",
            "summary": f"Notion API HTTP {error.code}: {error_body or error.reason}",
            "primary": None,
            "preview_lines": [],
            "resources": [],
            "anchors": {},
            "task_snapshot": {
                "status": "unavailable",
                "summary": f"Notion API HTTP {error.code}",
                "tasks": [],
            },
        }
    except URLError as error:
        reason = getattr(error, "reason", error)
        return {
            "status": "unavailable",
            "summary": f"koneksi ke Notion gagal: {reason}",
            "primary": None,
            "preview_lines": [],
            "resources": [],
            "anchors": {},
            "task_snapshot": {
                "status": "unavailable",
                "summary": f"koneksi ke Notion gagal: {reason}",
                "tasks": [],
            },
        }
    except Exception as error:
        return {
            "status": "unavailable",
            "summary": f"gagal mengambil data Notion: {error}",
            "primary": None,
            "preview_lines": [],
            "resources": [],
            "anchors": {},
            "task_snapshot": {
                "status": "unavailable",
                "summary": f"gagal mengambil data Notion: {error}",
                "tasks": [],
            },
        }
