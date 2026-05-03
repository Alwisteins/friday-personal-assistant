from google import genai
from google.genai import types
import ctypes
from datetime import datetime
import json
import os
import re
import shutil
from urllib import parse, request
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google_auth import fetch_upcoming_events

RESET = "\033[0m"
YOU_COLOR = "\033[94m"
FRIDAY_COLOR = "\033[95m"
RESPONSE_COLOR = "\033[37m"
DEFAULT_TIMEZONE = "Asia/Jakarta"
DEFAULT_LOCATION = "Sumur Batu, Jakarta Pusat, ID"
START_MY_DAY_PATTERNS = (
    "start my day",
    "good morning friday",
    "mulai hari",
    "mulai hariku",
    "brief pagi",
    "morning brief",
)
WEATHER_CODE_MAP = {
    0: "Clear",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with heavy hail",
}


def terminal_width():
    return shutil.get_terminal_size(fallback=(100, 30)).columns


def enable_ansi_colors():
    if os.name != "nt":
        return

    kernel32 = ctypes.windll.kernel32
    stdout = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint()
    if kernel32.GetConsoleMode(stdout, ctypes.byref(mode)):
        kernel32.SetConsoleMode(stdout, mode.value | 0x0004)


def show_startup_screen():
    ai_face = [
        "             ▒▓▓▓▓▓▓▓▓▓▓███▓▓▓▓▓▒▒▒▒             ",
        "         ▒▒▒██                     ██▓▒░         ",
        "       ▓▓█     ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    █▓▒       ",
        "      ▓█   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒   █▓      ",
        "     ██   ▓▓▓▓▓▒▒▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒  █▓     ",
        "    ██   ▓▓▓▓▓▓▒▒░░░░░░░░░░░░░░░░░▒▓▓▓▓▓▒  ██    ",
        "   ▓█▓  █▓█▓▒▒▒▓█▓▓███▓█████▓▓▓▓▓▒▒░░▒▒▓▓▓  █▓   ",
        "   ▓▓▓▓███▓▓▓███████████████████████▒░▒▒▓▓▓▓█▓   ",
        "   ▓▓▓▓███▓▓█████████████████████████▒░▒▓▒▓▒▓▓▒  ",
        "  ▓▓▓▓▓███▓██████████████████████████▓▒▒▓▒▓▒▒▓▒  ",
        "  ▓▓▓▓███▓▓█████▒▒▒▒▒▒▒███▒▒▒▒▒▒▒█████▒▒▓▒▓▒▒▓▒  ",
        "  ▓██▓███▓▓█████▒▒▒▒▒▒▒███▒▒▒▒▒▒▒█████▒▒▓▓█▓▓█▓  ",
        "  ████████▓█████▒▒▒▒▓▓▓███▓▓▓▒▒▒▒█████▒▒▓▓█▓▓█▓  ",
        "   ███████▓█████▒▒▒▒▓▓▓███▓▓▓▒▒▒▒█████▒▒▓▓█▓▓█▓  ",
        "     ▓▓███▓██████████████████████████▓▒▒▓▓▓▓     ",
        "        ██▓▓███████████▓▓▓████████████▓▒▓▓▓       ",
        "        ███▓▓███████████████████████▓▒▓▓▓        ",
        "         █▓█▓▓▓▓█████████████████▓▓▒▓▓▓▓         ",
        "           ▓████▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓███▓           ",
        "             ██████████████████████▓            ",
    ]

    width = terminal_width()
    print()
    for line in ai_face:
        print(line.center(width))
    print()
    print("Hi Alwi. Friday is here. What can I do for you today?".center(width))
    print()


def sanitize_terminal_output(text):
    if not text:
        return ""

    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        line = re.sub(r"^\s*#{1,6}\s*", "", line)
        line = re.sub(r"^\s*\*\s+", "- ", line)
        line = line.replace("**", "")
        line = re.sub(r"(?<=\s)\*(?=\S)", "", line)
        line = re.sub(r"(?<=\S)\*(?=\s)", "", line)
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()
    return cleaned_text or "(No response)"


def sanitize_stream_chunk(text):
    if not text:
        return ""

    chunk = text.replace("**", "")
    return chunk


def get_default_timezone():
    return os.getenv("FRIDAY_TIMEZONE", DEFAULT_TIMEZONE)


def get_default_location():
    return os.getenv("FRIDAY_LOCATION", DEFAULT_LOCATION)


def get_weather_query():
    return os.getenv("FRIDAY_WEATHER_QUERY", get_default_location())


def is_start_my_day_request(user_input):
    normalized = user_input.strip().lower()
    return any(pattern in normalized for pattern in START_MY_DAY_PATTERNS)


def fetch_json(url):
    with request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def get_day_period_label(hour):
    if 5 <= hour < 11:
        return "pagi"
    if 11 <= hour < 15:
        return "siang"
    if 15 <= hour < 18:
        return "sore"
    return "malam"


def get_current_time_snapshot():
    timezone_name = get_default_timezone()
    try:
        now = datetime.now(ZoneInfo(timezone_name))
        return {
            "status": "ok",
            "timezone": timezone_name,
            "formatted": now.strftime("%A, %d %B %Y %H:%M"),
            "hour": now.hour,
            "day_period": get_day_period_label(now.hour),
        }
    except Exception:
        now = datetime.now()
        return {
            "status": "fallback",
            "timezone": "local",
            "formatted": now.strftime("%A, %d %B %Y %H:%M"),
            "hour": now.hour,
            "day_period": get_day_period_label(now.hour),
        }


def build_weather_unavailable(location, reason):
    return {
        "status": "unavailable",
        "location": location,
        "summary": f"tidak dapat mengambil data ({reason})",
        "reason": reason,
    }


def fetch_weather_snapshot(location):
    try:
        geocode_url = (
            "https://geocoding-api.open-meteo.com/v1/search?"
            + parse.urlencode(
                {
                    "name": location,
                    "count": 1,
                    "language": "en",
                    "format": "json",
                }
            )
        )
        geocode_data = fetch_json(geocode_url)
        results = geocode_data.get("results") or []
        if not results:
            return build_weather_unavailable(location, "lokasi tidak ditemukan oleh layanan geocoding")

        place = results[0]
        resolved_name = ", ".join(
            part
            for part in [
                place.get("name"),
                place.get("admin1"),
                place.get("country_code"),
            ]
            if part
        )
        forecast_url = (
            "https://api.open-meteo.com/v1/forecast?"
            + parse.urlencode(
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,weather_code",
                    "timezone": "auto",
                    "forecast_days": 1,
                }
            )
        )
        forecast_data = fetch_json(forecast_url)
        current = forecast_data.get("current") or {}
        temperature = current.get("temperature_2m")
        weather_code = current.get("weather_code")
        description = WEATHER_CODE_MAP.get(weather_code, "Unknown")

        if temperature is None:
            return build_weather_unavailable(
                resolved_name or location,
                "respons cuaca tidak memuat temperatur saat ini",
            )

        # Keep ASCII-only output to avoid terminal encoding issues on Windows.
        return {
            "status": "ok",
            "location": resolved_name or location,
            "summary": f"{description}, {temperature} deg C",
            "source": "Open-Meteo",
        }

        return {
            "status": "ok",
            "location": resolved_name or location,
            "summary": f"{description}, {temperature}°C",
            "source": "Open-Meteo",
        }
    except HTTPError as error:
        return build_weather_unavailable(location, f"layanan cuaca merespons HTTP {error.code}")
    except TimeoutError:
        return build_weather_unavailable(location, "timeout saat menghubungi layanan cuaca")
    except URLError as error:
        reason = getattr(error, "reason", None) or "koneksi ke layanan cuaca gagal"
        return build_weather_unavailable(location, f"koneksi ke layanan cuaca gagal: {reason}")
    except KeyError as error:
        return build_weather_unavailable(location, f"field respons cuaca tidak lengkap: {error}")
    except (ValueError, json.JSONDecodeError):
        return build_weather_unavailable(location, "respons layanan cuaca tidak valid")


def build_start_my_day_prompt(user_input):
    location = get_default_location()
    weather_query = get_weather_query()
    time_snapshot = get_current_time_snapshot()
    weather_snapshot = fetch_weather_snapshot(weather_query)
    calendar_snapshot = fetch_upcoming_events()
    day_period = time_snapshot["day_period"]
    agenda_lines = format_calendar_snapshot(calendar_snapshot)

    live_data_lines = [
        "LIVE DATA",
        f"Waktu: {time_snapshot['formatted']} ({time_snapshot['timezone']})",
        f"Lokasi default: {location}",
        f"Cuaca ({weather_snapshot['location']}): {weather_snapshot['summary']}",
        f"Kalender: {calendar_snapshot['summary']}",
        "Agenda 24 jam ke depan:",
        *agenda_lines,
        "Aturan:",
        "- Gunakan hanya live data yang disediakan di atas untuk waktu, cuaca, dan kalender.",
        "- Jika ada field yang unavailable, katakan apa adanya.",
        "- Jika cuaca unavailable, sebutkan alasan spesifik yang tertulis di LIVE DATA. Jangan bilang data tidak disediakan aplikasi jika sebenarnya fetch cuaca gagal.",
        "- Jika kalender unavailable, sebutkan alasan spesifik yang tertulis di LIVE DATA.",
        "- Jangan mengarang data Notion, Calendar, atau Email jika belum ada data terhubung di pesan ini.",
        "- Gunakan format output yang konsisten dan terminal-friendly.",
        "- Untuk pembuka, gunakan struktur ini persis:",
        f"  Status {day_period}:",
        "  - Waktu: <isi dari LIVE DATA>",
        "  - Lokasi: <isi dari LIVE DATA>",
        "  - Cuaca: <isi dari LIVE DATA>",
        "  - Agenda: <ringkas isi dari LIVE DATA kalender>",
        f"- Setelah itu, tulis `Brief {day_period}:` lalu beri 2 sampai 4 poin actionable.",
        "- Jika ada agenda, prioritaskan agenda itu dalam brief.",
        f"- Jika cuaca relevan, masukkan saran praktis singkat di `Brief {day_period}:`.",
        f"- Pilih label waktu yang sesuai dengan jam pada LIVE DATA. Untuk jam {time_snapshot['formatted']}, gunakan `{day_period}`, bukan label waktu lain.",
        "",
        f"User request: {user_input}",
    ]
    return "\n".join(live_data_lines)


def format_calendar_snapshot(calendar_snapshot):
    if calendar_snapshot["status"] != "ok":
        return [f"- Unavailable: {calendar_snapshot['summary']}"]

    if not calendar_snapshot["events"]:
        return ["- Tidak ada agenda"]

    lines = []
    for event in calendar_snapshot["events"]:
        start_label = format_event_start(event["start"], event["is_all_day"])
        lines.append(f"- {start_label} {event['summary']}")
    return lines


def format_event_start(start_value, is_all_day):
    if is_all_day:
        return f"[All day {start_value}]"

    try:
        event_time = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
        return event_time.strftime("[%d %b %H:%M]")
    except ValueError:
        return f"[{start_value}]"


def extract_grounding_sources(response):
    if not response or not getattr(response, "candidates", None):
        return []

    sources = []
    seen = set()

    for candidate in response.candidates:
        grounding_metadata = getattr(candidate, "grounding_metadata", None)
        if not grounding_metadata:
            continue

        for chunk in grounding_metadata.grounding_chunks or []:
            web_chunk = getattr(chunk, "web", None)
            if not web_chunk or not web_chunk.uri:
                continue

            key = web_chunk.uri.strip()
            if key in seen:
                continue

            seen.add(key)
            sources.append(
                {
                    "title": (web_chunk.title or web_chunk.domain or web_chunk.uri).strip(),
                    "uri": key,
                }
            )

    return sources


def print_grounding_sources(response):
    sources = extract_grounding_sources(response)
    if not sources:
        return

    print(f"{FRIDAY_COLOR}FRIDAY ^o^ >{RESET} Sumber:")
    for index, source in enumerate(sources[:5], start=1):
        print(
            f"{FRIDAY_COLOR}FRIDAY ^o^ >{RESET} "
            f"{index}. {source['title']} - {source['uri']}"
        )


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

# Load system instruction dari file terpisah
system_instruction_path = os.path.join(os.path.dirname(__file__), "system_instruction.txt")
if not os.path.exists(system_instruction_path):
    raise FileNotFoundError("system_instruction.txt not found. Please create it.")
 
with open(system_instruction_path, "r", encoding="utf-8") as f:
    system_instruction = f.read()

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

client = genai.Client(api_key=api_key)
grounding_tool = types.Tool(google_search=types.GoogleSearch())

enable_ansi_colors()
show_startup_screen()

chat = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        tools=[grounding_tool],
    )
)

while True:
    user_input = input(f"{YOU_COLOR}YOU > {RESET}")
    if user_input.lower() in ["exit", "quit"]:
        print(f"{FRIDAY_COLOR}FRIDAY ^o^ >{RESET} Session terminated.")
        break

    prompt = build_start_my_day_prompt(user_input) if is_start_my_day_request(user_input) else user_input
    response = chat.send_message_stream(prompt)
    printed_prefix = False
    printed_content = False
    last_message = None

    for message in response:
        last_message = message
        if message.text:
            if not printed_prefix:
                print(
                    f"{FRIDAY_COLOR}FRIDAY ^o^ >{RESET} {RESPONSE_COLOR}",
                    end="",
                    flush=True,
                )
                printed_prefix = True

            chunk = sanitize_stream_chunk(message.text)
            if chunk:
                print(chunk, end="", flush=True)
                printed_content = True

    if printed_prefix:
        print(RESET)
        print_grounding_sources(last_message)
    elif not printed_content:
        print(f"{FRIDAY_COLOR}FRIDAY ^o^ >{RESET} (No response)")
