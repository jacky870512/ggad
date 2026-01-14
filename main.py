import requests
import time
import os
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# ==================== 配置區 ====================
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")  # 建議用環境變數！不要硬寫
if not WEBHOOK_URL:
    WEBHOOK_URL = "https://discordapp.com/api/webhooks/1460271199341904025/OzgSEIgrXSsME-mVpdtsXz1oGp5sR56Ncqa-z5YmmrpGgnZNw55RXhSWDAbroCbaHavG"  # 測試時臨時用，之後刪除

API_URL = "https://api.exptech.dev/v1/earthquake?type=report"
CHECK_INTERVAL = 12  # 秒，建議 10~15 秒，避免過載
PING_THRESHOLD_MAG = 5.5   # 規模超過這個才 @everyone
PING_THRESHOLD_INT = 5     # 最大震度超過這個才 @everyone

# 可選：記錄到檔案（放在同目錄 log.txt）
LOG_FILE = "earthquake_log.txt"

# ==================== 發送函式 ====================
def send_to_discord(message):
    payload = {
        "content": message,
        "username": "台灣地震速報 Bot",
        "avatar_url": "https://i.imgur.com/8ZfZfZf.png"  # 建議換成地震相關 icon
    }
    
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code in (200, 204):
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 成功推播")
            return True
        else:
            print(f"推播失敗 {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"發送錯誤: {e}")
        return False

# ==================== 主邏輯 ====================
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    reraise=True
)
def fetch_earthquake():
    response = requests.get(API_URL, timeout=10)
    response.raise_for_status()
    return response.json()

print("地震監測程式已啟動... (Ctrl+C 結束)")
last_eq_time = None  # 用時間輔助判斷新事件（更穩）

while True:
    try:
        data = fetch_earthquake()

        if not data:
            time.sleep(CHECK_INTERVAL)
            continue

        eq = data[0]  # 最新一筆
        eq_time = eq.get("time", "未知")

        # 判斷是否新地震（優先用 time，其次用 id）
        if last_eq_time == eq_time:
            time.sleep(CHECK_INTERVAL)
            continue

        last_eq_time = eq_time

        # 提取資訊（加防呆）
        magnitude = float(eq.get("magnitude", 0)) if eq.get("magnitude") else 0
        depth = eq.get("depth", "?")
        loc = eq.get("loc", "未知位置")
        lat = eq.get("lat", "?")
        lon = eq.get("lon", "?")
        max_int_str = eq.get("intensity", "?")
        max_int = int(max_int_str) if max_int_str.isdigit() else 0

        epicenter = f"{loc} ({lat}°N, {lon}°E)" if lat != "?" and lon != "?" else loc

        # 嘗試找是否有縣市震度（目前大多數情況沒有，留空或顯示提示）
        areas = eq.get("areas", [])  # 如果未來有這個欄位就會顯示
        intensity_detail = ""
        if areas:
            intensity_detail = "**各區域震度**（部分或預估）:\n"
            for area in areas[:8]:  # 只顯示前8個避免太長
                name = area.get("area", "?")
                int_level = area.get("intensity", "?")
                intensity_detail += f"- {name}：{int_level}級\n"
            if len(areas) > 8:
                intensity_detail += "...及其他地區（詳細請看氣象署官網）\n"
        else:
            intensity_detail = "（目前僅提供最大預估震度，詳細各縣市震度請參考中央氣象署稍後發布的正式報告）\n"

        # 決定是否 @everyone
        should_ping = (magnitude >= PING_THRESHOLD_MAG) or (max_int >= PING_THRESHOLD_INT)
        ping_text = "@everyone\n\n" if should_ping else ""

        # 組合訊息
        message = f"""{ping_text}**【地震速報 - 新事件】**
🕒 **發生時間**：{eq_time}
🌍 **震央**：{epicenter}
⚡ **規模**：M{magnitude:.1f}
📏 **深度**：{depth} km
💥 **最大預估震度**：**{max_int_str} 級**

{intensity_detail}
🔗 {eq.get('url', 'https://www.cwa.gov.tw/V8/E/E/index.html')}

請保持冷靜，注意安全！
"""

        # 發送
        if send_to_discord(message):
            # 可選：記錄 log
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(f"[{datetime.now()}] 推播成功: {eq_time} M{magnitude}\n")
            except:
                pass

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 主迴圈錯誤: {e}")
        time.sleep(30)  # 重大錯誤等久一點


    time.sleep(CHECK_INTERVAL)
