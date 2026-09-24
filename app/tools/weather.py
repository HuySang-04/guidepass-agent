import requests
from app import config

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

def get_hourly_weather(lat, lon, date):
    resp = requests.get(
        OPEN_METEO_URL,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "precipitation_probability,apparent_temperature,precipitation",
            "timezone": "Asia/Ho_Chi_Minh",
            "start_date": date,
            "end_date": date,
        },
        timeout=12,
    )

    resp.raise_for_status()
    hourly = resp.json()['hourly']
    return {
        "date": date,
        "hourly": [
            {
                "time": t,
                "precipitation_probability_pct": prob,
                "apparent_temperature_c": temp,
                "precipitation_mm": rain,
                "avoid_outdoor": (
                    (prob is not None and prob >= config.RAIN_PROB_AVOID_PCT)
                    or (temp is not None and temp >= config.HOT_APPARENT_C)
                ),
            }
            for t, prob, temp, rain in zip(
                hourly["time"],
                hourly["precipitation_probability"],
                hourly["apparent_temperature"],
                hourly["precipitation"],
            )
        ],
    }
