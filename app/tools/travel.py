import requests
from datetime import time
from datetime import datetime, time as dtime
from app import config

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"

def parse_hhmm(s):
    """Parse chuỗi 'HH:MM' thành datetime.time an toàn."""
    try:
        parts = s.split(':')
        return dtime(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        raise ValueError(f"Định dạng thời gian không hợp lệ: '{s}'. Vui lòng dùng 'HH:MM'")

def is_time_in_range(check_time, start, end):
    if start <= end:
        return start <= check_time < end
    return check_time >= start or check_time < end

def travel_minutes(base_min, depart, rain_mm_h):
    factor = 1.0
    
    # Kiểm tra giờ cao điểm
    is_rush = any(is_time_in_range(depart, start, end) for start, end in config.RUSH_HOURS)
    if is_rush:
        factor *= config.RUSH_HOUR_FACTOR
        
    # Kiểm tra mưa
    if rain_mm_h >= config.RAIN_MM_SLOWDOWN_THRESHOLD:
        factor *= config.RAIN_SLOWDOWN_FACTOR
        
    return base_min * factor, is_rush

def get_travel_time(origin_lat, origin_lon, dest_lat, dest_lon, depart_time, rain_mm_h = 0.0):
    url = OSRM_URL.format(lon1=origin_lon, lat1=origin_lat, lon2=dest_lon, lat2=dest_lat)
    
    try:
        resp = requests.get(url, params={'overview': 'false'}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Lỗi kết nối OSRM API: {e}")

    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError(f"OSRM không tìm được tuyến đường phù hợp: {data.get('code')}")

    base_min = data['routes'][0]['duration'] / 60.0
    depart = parse_hhmm(depart_time)
    
    adjusted_min, is_rush = travel_minutes(base_min, depart, rain_mm_h)

    return {
        "base_minutes": round(base_min, 1),
        "adjusted_minutes": round(adjusted_min, 1),
        "is_rush_hour": is_rush,
        "rain_mm_h": rain_mm_h,
        "source": "osrm-demo + rush/rain heuristic",
        "note": "Kết quả dựa trên ước tính giả định, không phải dữ liệu giao thông thực tế.",
    }
