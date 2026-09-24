import json
import logging
from datetime import date as ddate

from openai import OpenAI
from pydantic import ValidationError

from app import config
from app.schemas import Itinerary
from app.session import Session, trim_history
from app.tools import places, travel, weather

logger = logging.getLogger("guidepass.llm")

MAX_TOOL_ROUNDS = 32  
LLM_TIMEOUT = 45 

client = OpenAI(api_key=config.LLM_API_KEY or "unused", base_url=config.LLM_BASE_URL, timeout=LLM_TIMEOUT)

TOOL_IMPL = {
    "geocode": lambda a: places.geocode(a["address"]),
    "search_places": lambda a: places.search_places(**a),
    "get_weather": lambda a: weather.get_hourly_weather(**a),
    "get_travel_time": lambda a: travel.get_travel_time(**a),
}

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'geocode',
            'description': (
                'Convert a specific Vietnamese place name or address into latitude/longitude coordinates. '
                'Pass only the exact place name (e.g., "Chợ Bến Thành", "Landmark 81"), preserving the diacritics.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Specify the exact place name or address."}
                },
                "required": ["address"],  
            },
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_places',
            'description': (
                'Find locations near the coordinates. '
                'Pass category, near_lat, near_lon, and radius_m.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["attraction", "restaurant", "cafe", "food", "museum"]},
                    "near_lat": {"type": "number"},
                    "near_lon": {"type": "number"},
                    "radius_m": {"type": "integer", "default": 5000},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["category", "near_lat", "near_lon"],
            },
        }
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_weather',
            'description': 'Weather forecast at 2-hour intervals throughout the day (00:00, 02:00, 04:00, 06:00...) for a specific coordinate.',
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["lat", "lon", "date"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_travel_time",
            "description": "Travel time between two coordinates based on departure time (OSRM + peak hour/rain factor).",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_lat": {"type": "number"},
                    "origin_lon": {"type": "number"},
                    "dest_lat": {"type": "number"},
                    "dest_lon": {"type": "number"},
                    "depart_time": {"type": "string", "description": "HH:MM"},
                    "rain_mm_h": {"type": "number", "description": "Get from get_weather, default 0"},
                },
                "required": ["origin_lat", "origin_lon", "dest_lat", "dest_lon", "depart_time"],
            },
        },
    },
{
        "type": "function",
        "function": {
            "name": "respond_with_itinerary",
            "description": (
                "FINAL response to the user. ALWAYS end the turn by calling this tool, "
                "even when refusing due to insufficient data or answering a question without a new itinerary. "
                "Every item in 'stops' MUST contain EXACTLY these keys (do not rename, omit, or add extra keys):\n"
                '{"name": str, "category": str, "indoor": bool, "lat": float, "lon": float, '
                '"arrive": "HH:MM", "leave": "HH:MM", "travel_minutes_from_prev": int, '
                '"weather_note": str, "reason": str, "source": str}\n'
                "Example of a valid stop item:\n"
                '{"name": "Bảo Tàng Địa Chất", "category": "museum", "indoor": true, '
                '"lat": 10.7849957, "lon": 106.7076753, "arrive": "12:00", "leave": "13:30", '
                '"travel_minutes_from_prev": 2, "weather_note": "Indoor, avoid midday rain", '
                '"reason": "Matches history interest, cheap ticket", "source": "osm:node/1001114513"}'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reply": {"type": "string", "description": "Natural response message in Vietnamese for the user."},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "stops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "category": {"type": "string"},
                                "indoor": {"type": "boolean"},
                                "lat": {"type": "number"},
                                "lon": {"type": "number"},
                                "arrive": {"type": "string"},
                                "leave": {"type": "string"},
                                "travel_minutes_from_prev": {"type": "integer"},
                                "weather_note": {"type": "string"},
                                "reason": {"type": "string"},
                                "source": {"type": "string"},
                            },
                            "required": [
                                "name", "category", "indoor", "lat", "lon", "arrive", "leave",
                                "travel_minutes_from_prev", "weather_note", "reason", "source",
                            ],
                        },
                    },
                },
                "required": ["reply", "date", "stops"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are GuidePass's AI travel itinerary assistant for {city}. Today is {today}.

MANDATORY RULES:
1. Never invent a place, coordinates, opening hours, or travel time. Every stop must come from the results returned by search_places (keep the exact "source" field returned by that tool).
1a. Full-day itinerary (no existing itinerary yet, or "Current itinerary" = "none yet"): every stop must include arrival time, departure time, travel_minutes_from_prev, weather_note, and a reason for the choice (matching the user's stated interests and budget).
2. Typical sequence: geocode the starting point if coordinates aren't known yet -> search_places to find candidates -> get_weather for that date -> get_travel_time for each leg, using the actual planned departure time (never guess). When geocoding, ALWAYS keep Vietnamese diacritics exactly as the user typed them (e.g. "Chợ Bến Thành", not "Cho Ben Thanh") — OpenStreetMap data uses proper diacritics. Only re-geocode if the starting point changes; do not call geocode/get_weather again just because the user is editing part of the itinerary.
2b. If the user only gives an approximate landmark/area (e.g. "hotel near Bến Thành Market", "near District 1") instead of an exact address, do NOT stop to ask for more details — geocode that landmark directly and use it as the starting point. Only ask the user for clarification when there is truly no location reference at all to geocode.
2c. search_places: call it WITHOUT a keyword first to see what's actually nearby, then pick from the returned list based on the user's preferences. Do NOT guess the name of a specific museum/restaurant and call search_places repeatedly with different keywords trying to find that exact place — OSM data is incomplete, guessed names usually won't match, and each extra call wastes a round-trip and response time. If a broad search returns nothing suitable, pick the closest/most reasonable candidate from the list instead of searching further. Only make an additional search_places call (new category) when the user asks to switch to a category not searched yet (e.g. "vegetarian restaurant"); never repeat a category already searched.
3. If avoid_outdoor=true at the planned time (strong sun or high chance of rain), prioritize indoor=true stops or shift the time; state the reason clearly in weather_note. When the user reports bad weather for a specific time window (e.g. "heavy rain in the afternoon"), treat avoid_outdoor=true for just that window, even if the overall day's weather assessment differs.
4. travel_minutes_from_prev must always come from get_travel_time (use adjusted_minutes). When the user compares multiple departure times, call the tool multiple times and clearly state that this is an OSRM estimate + rush-hour/rain heuristic, not real-time traffic; specify which number corresponds to which departure time.
5. When the user asks to edit only part of the plan (change 1 stop, change the afternoon, etc.), change ONLY that part, keeping all other stops from the "Current itinerary" below unchanged (times, notes, reasons — do not rewrite them). Do not recompute from scratch. Prior constraints (free time window, budget, interests, mobility restrictions if already stated) still apply to the edited part. Only recompute travel_minutes for the legs adjacent to the part that changed.
6. If search_places returns no suitable results, be honest that there's no data available — do NOT make up a place. Still call respond_with_itinerary (stops may be empty or the previous itinerary retained), and explain this in the reply.
7. Elderly companions / limited walking ability / children: fewer stops, shorter travel distances, prioritize cars/rides, include rest stops between locations. Apply this for all subsequent turns in this session too, even if the information arrives after the initial itinerary was created.
8. ALWAYS end the turn by calling respond_with_itinerary — even when simply answering a question (e.g., about travel time) with no new itinerary, in which case keep the existing stops.

Current itinerary for this session (used as the base if the user requests an edit; "none yet" means none has been created):
{current_itinerary}
"""

def _tool_result(name, args):
    impl = TOOL_IMPL.get(name)
    if impl is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return impl(args)
    except Exception as e: 
        return {"error": str(e)}


def _try_parse_itinerary_json(content=None):
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "stops" not in data:
        return None
    try:
        itinerary = Itinerary(date=data.get("date", ddate.today().isoformat()), stops=data["stops"])
    except ValidationError:
        return None
    reply_text = data.get("reply") or "Đây là lịch trình mình đề xuất."
    return reply_text, itinerary.model_dump()


def run_turn(user_message, session: Session):
    today = ddate.today().isoformat()
    system = {
        "role": "system",
        "content": SYSTEM_PROMPT.format(
            city=config.DEFAULT_CITY,
            today=today,
            current_itinerary=json.dumps(session.itinerary, ensure_ascii=False) if session.itinerary else "chưa có",
        ),
    }
    
    messages = [system] + session.messages + [{"role": "user", "content": user_message}]
    searched_categories = set()

    print(f"\n🤖 Người dùng hỏi: {user_message}\n" + "-"*40)

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.info("round %d: calling LLM (%d messages)", round_num, len(messages))
        
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        
        response_message = resp.choices[0].message
        messages.append(response_message.model_dump(exclude_none=True))

        if not response_message.tool_calls:
            recovered = _try_parse_itinerary_json(response_message.content)
            if recovered is not None:
                logger.info("round %d: no tool call, but content was itinerary JSON — recovered", round_num)
                reply_text, itinerary_dict = recovered
                session.itinerary = itinerary_dict
                session.messages = trim_history(messages[1:])
                return reply_text, itinerary_dict
            
            logger.info("round %d: no tool call, ending turn", round_num)
            session.messages = trim_history(messages[1:])
            return response_message.content or "", session.itinerary

        final_reply = None
        final_itinerary = None

        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            try:
                function_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                function_args = {}
            
            print(f"🔧 LLM gọi Tool: [{function_name}] (Vòng {round_num})")
            print(f"📦 Tham số truyền vào: {json.dumps(function_args, ensure_ascii=False)}")

            if function_name == "respond_with_itinerary":
                try:
                    itinerary = Itinerary(date=function_args.get("date", today), stops=function_args.get("stops", []))
                except ValidationError as e:
                    print(f"Lỗi Schema Itinerary: {e}")
                    messages.append({
                        "role": "tool", 
                        "tool_call_id": tool_call.id, 
                        "name": function_name,
                        "content": json.dumps({"error": f"schema invalid: {e}"})
                    })
                    continue
                
                final_reply = function_args.get("reply", "")
                final_itinerary = itinerary.model_dump()
                messages.append({
                    "role": "tool", 
                    "tool_call_id": tool_call.id, 
                    "name": function_name,
                    "content": "ok"
                })
                print(f"✅ Đã nhận lịch trình hợp lệ qua 'respond_with_itinerary'.\n" + "-"*40)
                continue

            if function_name == 'search_places':
                category = function_args.get('category')
                if category in searched_categories:
                    tool_result = {
                        "warning": f"Category '{category}' has already been searched for. Please use existing results."
                    }
                else:
                    searched_categories.add(category)
                    tool_result = _tool_result(function_name, function_args)

            if function_name in TOOL_IMPL:
                tool_result = _tool_result(function_name, function_args)
            else:
                tool_result = {"error": f"Tool {function_name} does not exist."}

            count_val = tool_result.get('count', 'N/A') if isinstance(tool_result, dict) else 'N/A'
            print(f"✅ Kết quả trả về từ Tool [{function_name}]: count = {count_val}")
            print("=" * 100)
            
            tool_content_str = json.dumps(tool_result, ensure_ascii=False, default=str)
            if len(tool_content_str) > 3000:
                tool_result = {"status": "success", "summary": "Data truncated to save tokens", "count": tool_result.get('count', 0)}
                tool_content_str = json.dumps(tool_result, ensure_ascii=False)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": tool_content_str
            })

        if final_itinerary is not None:
            session.itinerary = final_itinerary
            session.messages = trim_history(messages[1:])
            return final_reply, final_itinerary

    logger.warning("hit MAX_TOOL_ROUNDS (%d) without a final respond_with_itinerary call", MAX_TOOL_ROUNDS)
    session.messages = trim_history(messages[1:])
    print(f"⚠️ Đã đạt giới hạn MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) mà chưa gọi xong respond_with_itinerary.")
    return "Xin lỗi, mình chưa xử lý xong yêu cầu này, bạn hỏi lại giúp mình nhé.", session.itinerary