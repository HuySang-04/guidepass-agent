import os
from datetime import time
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "contact@example.com")
USER_AGENT = f"GuidePassTripAgent/0.1 ({CONTACT_EMAIL})"

HTTP_TIMEOUT = 12 

DEFAULT_CITY = "Ho Chi Minh City, Vietnam"

HOT_APPARENT_C = 35.0     
RAIN_PROB_AVOID_PCT = 50  

RUSH_HOURS = [(time(7, 0), time(9, 0)), (time(16, 30), time(19, 0))]
RUSH_HOUR_FACTOR = 1.6     
RAIN_SLOWDOWN_FACTOR = 1.3 
RAIN_MM_SLOWDOWN_THRESHOLD = 2.0