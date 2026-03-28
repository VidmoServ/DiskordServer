# bot/config.py

TOKEN = "MTM4MjM3Njg1MDk5ODgyNDk5MA.Gum-Wj.S_VLsBbUUeTxdQoq5rbPS4k9cDVFKCH9mGX-Fs"
GUILD_ID = 1426563806213177508  # ID Twojego serwera Discord

# Ścieżki do plików
DATA_DIR = "data"
ECONOMY_FILE = f"{DATA_DIR}/economy.json"
TIKTOK_FILE = f"{DATA_DIR}/tracked_accounts.json"
LOG_CHANNEL_ID = 1486183581868097596  # ID kanału, na który mają iść logi TikToka

# ID Twojego konta Discord (admin)
ADMIN_ID = 123456789012345678787697191435108372  # <- podmień

# Kanały logów (0 = wyłączone)
LOG_CHANNEL_ID = 0
ERROR_CHANNEL_ID = 0

# Dashboard
DASHBOARD_PORT = 8080
DASHBOARD_KEY = "api_32f9df48-b98a-4379-9f99-ad060af74164"  # zmień na coś losowego
API_VERSION_ID = "apiversion_7dd31e60-1ac9-420a-a191-2437fc191b67"
TIKTOK_API_URL = "https://www.tiktok.com/@_nadia_b1436?is_from_webapp=1&sender_device=pc" # ustaw URL dostawcy
TIKTOK_API_AUTH_TYPE = "ApiKey"  # "Bearer" lub "ApiKey"



# Limity
PREMIUM_LIMIT_PER_USER = 10
GLOBAL_LIMIT = 200

# Debug API
TIKTOK_API_DEBUG = False
TIKTOK_API_DEBUG_FILE = "tiktok_api_debug.log"  # zapis w katalogu Bot V2
