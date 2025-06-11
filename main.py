from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai, json
from flatlib import const
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from dotenv import load_dotenv
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime
import asyncio
import aiohttp

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")
ASTRO_CHANNEL_ID = os.getenv("ASTRO_CHANNEL_ID", "@moyanatalkarta")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    KeyboardButton("🚀 Начать расчёт"),
    KeyboardButton("📘 Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "🔮 Рассчитать", "📄 Скачать PDF", "📝 Заказать подробный отчёт"
)

users = {}
admin_id = 7943520249
processing_users = set()
USERS_FILE = os.path.join("/data" if os.getenv("RENDER") else ".", "users.json")
users_lock = asyncio.Lock()

def load_users():
    """Загрузка данных пользователей из JSON."""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for user_id, info in data.items():
                    if "dt_utc" in info:
                        info["dt_utc"] = datetime.fromisoformat(info["dt_utc"])
                logging.info(f"Loaded {len(data)} users from {USERS_FILE}: {list(data.keys())}")
                return data
        logging.info(f"No {USERS_FILE} found, starting with empty users")
        return {}
    except Exception as e:
        logging.error(f"Error loading users from {USERS_FILE}: {e}", exc_info=True)
        return {}

async def save_users():
    """Сохранение данных пользователей в JSON с блокировкой."""
    async with users_lock:
        try:
            data = {}
            for user_id, info in users.items():
                data[user_id] = info.copy()
                if "dt_utc" in data[user_id]:
                    data[user_id]["dt_utc"] = data[user_id]["dt_utc"].isoformat()
            os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"Saved {len(data)} users to {USERS_FILE}: {list(data.keys())}")
        except Exception as e:
            logging.error(f"Error saving users to {USERS_FILE}: {e}", exc_info=True)
            # Попытка сохранить в /tmp/
            try:
                tmp_file = "/tmp/users.json"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logging.info(f"Saved {len(data)} users to fallback {tmp_file}")
            except Exception as e2:
                logging.error(f"Error saving to fallback {tmp_file}: {e2}", exc_info=True)

# Инициализация users при старте
users = load_users()

async def clear_webhook():
    """Удаление существующего вебхука с повторными попытками."""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{API_TOKEN}/getWebhookInfo"
                async with session.get(url) as response:
                    if response.status != 200:
                        logging.error(f"Failed to get webhook info on attempt {attempt}: {await response.text()}")
                        continue
                    webhook_info = await response.json()
                    logging.info(f"Webhook info on attempt {attempt}: {webhook_info}")
                    if webhook_info.get("result", {}).get("url"):
                        url_delete = f"https://api.telegram.org/bot{API_TOKEN}/deleteWebhook"
                        async with session.get(url_delete) as delete_response:
                            if delete_response.status == 200:
                                logging.info(f"Webhook deleted successfully on attempt {attempt}")
                                return
                            else:
                                logging.error(f"Failed to delete webhook on attempt {attempt}: {await delete_response.text()}")
                    else:
                        logging.info("No webhook configured")
                        return
        except Exception as e:
            logging.error(f"Error clearing webhook on attempt {attempt}: {e}", exc_info=True)
        await asyncio.sleep(1)
    logging.error("Failed to clear webhook after all attempts")

def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

def get_house_manually(chart, lon):
    """Ручное определение дома по долготе."""
    try:
        for house in chart.houses:
            start_lon = house.lon
            end_lon = (house.lon + house.size) % 360
            if start_lon <= end_lon:
                if start_lon <= lon <= end_lon:
                    return house.id
            else:
                if lon >= start_lon or lon <= end_lon:
                    return house.id
        logging.error(f"No house found for longitude {lon}")
        return None
    except Exception as e:
        logging.error(f"Error getting house for longitude {lon}: {e}", exc_info=True)
        return None

def get_aspects(chart, planet_names):
    """Получение аспектов между планетами."""
    aspects = []
    try:
        if not chart or not hasattr(chart, 'objects'):
            logging.error("Chart not properly initialized or missing objects")
            return aspects
        for p in planet_names:
            obj = chart.get(p)
            if obj and hasattr(obj, 'lon'):
                logging.info(f"Planet {p} found at longitude {obj.lon:.2f}°")
            else:
                logging.error(f"Planet {p} not found or missing longitude")
        for i, p1 in enumerate(planet_names):
            obj1 = chart.get(p1)
            if not obj1 or not hasattr(obj1, 'lon'):
                logging.warning(f"Skipping {p1}: not found or missing longitude")
                continue
            for p2 in planet_names[i + 1:]:
                obj2 = chart.get(p2)
                if not obj2 or not hasattr(obj2, 'lon'):
                    logging.warning(f"Skipping {p2}: not found or missing longitude")
                    continue
                try:
                    diff = abs(obj1.lon - obj2.lon)
                    diff = min(diff, 360 - diff)
                    logging.info(f"Angle between {p1} ({obj1.lon:.2f}°) and {p2} ({obj2.lon:.2f}°): {diff:.2f}°")
                    orb = 15
                    if abs(diff - 0) <= orb:
                        aspects.append((p1, p2, diff, "соединение"))
                    elif abs(diff - 60) <= orb:
                        aspects.append((p1, p2, diff, "секстиль"))
                    elif abs(diff - 90) <= orb:
                        aspects.append((p1, p2, diff, "квадрат"))
                    elif abs(diff - 120) <= orb:
                        aspects.append((p1, p2, diff, "тригон"))
                    elif abs(diff - 180) <= orb:
                        aspects.append((p1, p2, diff, "оппозиция"))
                except Exception as e:
                    logging.error(f"Error calculating aspect between {p1} and {p2}: {e}", exc_info=True)
        logging.info(f"Aspects calculated: {aspects}")
        return aspects
    except Exception as e:
        logging.error(f"Error in get_aspects: {e}", exc_info=True)
        return []

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Нажми кнопку ниже, чтобы начать расчёт.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(commands=["debug"])
async def debug(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id != str(admin_id):
        await message.answer("⚠️ Доступ запрещен.")
        return
    global users
    users = load_users()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            json_content = f.read()
    except Exception as e:
        json_content = f"Error reading {USERS_FILE}: {e}"
    await message.answer(
        f"Users in memory: {list(users.keys())}\n"
        f"Users.json content:\n{json_content}",
        parse_mode="Markdown"
    )
    logging.info(f"Debug requested by {user_id}: {list(users.keys())}")

@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📘 Пример платного отчёта")
async def send_example_report(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f, caption="📘 Пример платного отчёта")
    except FileNotFoundError:
        logging.error("Example report file not found")
        await message.answer("⚠️ Пример отчёта не найден. Обратитесь к администратору.")

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf_handler(message: types.Message):
    user_id = str(message.from_user.id)
    global users
    users = load_users()
    logging.info(f"PDF request for user {user_id}. Users loaded: {list(users.keys())}")
    if user_id in users and "pdf" in users[user_id]:
        try:
            with open(users[user_id]["pdf"], "rb") as f:
                await message.answer_document(f)
        except FileNotFoundError:
            logging.error(f"PDF file {users[user_id]['pdf']} not found")
            await message.answer("⚠️ PDF не найден.")
    else:
        await message.answer("Сначала рассчитайте карту.")

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id in processing_users:
        logging.warning(f"User {user_id} already processing")
        await message.answer("⏳ Ваш запрос уже обрабатывается, пожалуйста, подождите.")
        return

    try:
        processing_users.add(user_id)
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            logging.error("Invalid input format")
            await message.answer("⚠️ Неверный формат. Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        logging.info(f"Input: {date_str}, {time_str}, {city}")
        try:
            geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
            if not geo.get("results", []):
                logging.error(f"No geocode data found for city {city}")
                await message.answer("❌ Город не найден.")
                return
            lat = geo["results"][0]["geometry"].get("lat", 0.0)
            lon = geo["results"][0]["geometry"].get("lng", 0.0)
        except Exception as e:
            logging.error(f"Error accessing geocode data: {e}", exc_info=True)
            await message.answer("❌ Ошибка при получении координат города. Попробуйте снова или уточните город.")
            return

        lat_str = decimal_to_dms_str(lat, True)
        lon_str = decimal_to_dms_str(lon, False)
        logging.info(f"Coordinates: lat={lat_str}, lon={lon_str}")

        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if not timezone_str:
            logging.warning("Timezone not found for coordinates")
            await message.answer("❌ Не удалось определить часовой пояс.")
            return
        logging.info(f"Timezone: {timezone_str}")

        timezone = pytz.timezone(timezone_str)
        try:
            dt_input = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        except ValueError as e:
            logging.error(f"Invalid datetime format: {date_str} {time_str}: {e}")
            await message.answer("⚠️ Неверный формат даты или времени.")
            return
        dt_local = timezone.localize(dt_input)
        dt_utc = dt_local.astimezone(pytz.utc)
        dt = Datetime(dt_utc.strftime("%Y/%m/%d"), dt_utc.strftime("%H:%M"), "+00:00")
        logging.info(f"UTC Time: {dt_utc}")

        try:
            chart = Chart(dt, GeoPos(lat_str, lon_str))
            logging.info(f"Chart created with houses: {chart.houses}")
        except Exception as e:
            logging.error(f"Error creating chart: {e}", exc_info=True)
            await message.answer("❌ Ошибка при создании натальной карты.")
            return

        planet_names = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        planet_info = {}
        aspects = get_aspects(chart, planet_names)
        aspects_by_planet = {p: [] for p in planet_names}
        for p1, p2, diff, aspect_name in aspects:
            aspects_by_planet[p1].append(f"{p1} {aspect_name} {p2} ({round(diff, 1)}°)")
            aspects_by_planet[p2].append(f"{p2} {aspect_name} {p1} ({round(diff, 1)}°)")
        logging.info(f"Aspects by planet: {aspects_by_planet}")

        for p in planet_names:
            try:
                obj = chart.get(p)
                if not obj:
                    logging.error(f"Planet {p} not found in chart")
                    await message.answer(f"⚠️ Планета {p} не найдена в карте.")
                    continue
                sign = getattr(obj, "sign", "Unknown")
                deg = getattr(obj, "lon", 0.0)
                house = get_house_manually(chart, deg)
                logging.info(f"Processing planet: {p}, Sign: {sign}, Deg: {deg:.2f}, House: {house}")

                prompt = f"{p} в знаке {sign}, дом {house}. Дай краткую астрологическую интерпретацию."
                try:
                    res = openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.7,
                        max_tokens=500
                    )
                    if res.choices:
                        reply = res.choices[0].message.content.strip()
                    else:
                        reply = "Не удалось получить интерпретацию: пустой ответ."
                        logging.warning(f"Empty GPT response for {p}")
                except Exception as e:
                    logging.error(f"Error in GPT interpretation for {p}: {e}", exc_info=True)
                    reply = "Не удалось получить интерпретацию."

                aspect_text = "\n".join([f"• {a}" for a in aspects_by_planet[p]]) if aspects_by_planet[p] else "• Нет точных аспектов"
                output = f"🔍 **{p}** в {sign}, дом {house}\n📩 {reply}\n📐 Аспекты:\n{aspect_text}\n"
                try:
                    await message.answer(output, parse_mode="Markdown")
                    await asyncio.sleep(1.0)
                except Exception as e:
                    logging.error(f"Error sending message for {p}: {e}", exc_info=True)
                    await message.answer(f"⚠️ Ошибка при отправке данных для {p}.")

                pdf_output = f"[Положение] {p} в {sign}, дом {house}\n[Интерпретация] {reply}\n[Аспекты]\n{aspect_text}\n"
                summary.append(pdf_output)
                planet_info[p] = {
                    "sign": sign,
                    "degree": deg,
                    "house": house
                }
            except Exception as e:
                logging.error(f"Error processing planet {p}: {e}", exc_info=True)
                await message.answer(f"⚠️ Ошибка при обработке {p}: {e}")
                continue

        # Расчет Асцендента
        try:
            ascendant = chart.get(const.ASC)
            asc_sign = getattr(ascendant, "sign", "Unknown")
            logging.info(f"Ascendant calculated: {asc_sign}")

            prompt = f"Асцендент в знаке {asc_sign}. Дай краткую астрологическую интерпретацию."
            try:
                res = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=500
                )
                if res.choices:
                    asc_reply = res.choices[0].message.content.strip()
                else:
                    asc_reply = "Не удалось получить интерпретацию: пустой ответ."
                    logging.warning("Empty GPT response for Ascendant")
            except Exception as e:
                logging.error(f"Error in GPT interpretation for Ascendant: {e}", exc_info=True)
                asc_reply = "Не удалось получить интерпретацию."

            asc_output = f"🔍 **Асцендент** в {asc_sign}\n📩 {asc_reply}\n"
            try:
                await message.answer(asc_output, parse_mode="Markdown")
                await asyncio.sleep(1.0)
            except Exception as e:
                logging.error(f"Error sending message for Ascendant: {e}", exc_info=True)
                await message.answer("⚠️ Ошибка при отправке данных для Асцендента.")

            asc_pdf_output = f"[Положение] Асцендент в {asc_sign}\n[Интерпретация] {asc_reply}\n"
            summary.append(asc_pdf_output)
            planet_info["Ascendant"] = {"sign": asc_sign}
        except Exception as e:
            logging.error(f"Error processing Ascendant: {e}", exc_info=True)
            await message.answer(f"⚠️ Ошибка при обработке Асцендента: {e}")

        try:
            logging.info(f"Summary for PDF: {summary}")
            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            for line in summary:
                if not isinstance(line, str):
                    logging.error(f"Invalid summary item: {line}")
                    line = str(line)
                for chunk in [line[i:i+200] for i in range(0, len(line), 200)]:
                    pdf.multi_cell(0, 10, chunk)
            pdf_path = f"/tmp/user_{user_id}_report.pdf" if os.getenv("RENDER") else f"user_{user_id}_report.pdf"
            pdf.output(pdf_path)
            logging.info(f"PDF created: {pdf_path}")
        except Exception as e:
            logging.error(f"Error creating PDF: {e}", exc_info=True)
            await message.answer(f"❌ Ошибка при создании PDF: {e}")
            return

        users[user_id] = {
            "pdf": pdf_path,
            "planets": planet_info,
            "lat": lat,
            "lon": lon,
            "city": city,
            "date_str": date_str,
            "time_str": time_str,
            "dt_utc": dt_utc
        }
        await save_users()
        logging.info(f"User data saved for {user_id}: {users[user_id]}")

        # Предложение подписки для подробного отчета
        subscription_kb = InlineKeyboardMarkup(row_width=1)
        subscription_kb.add(
            InlineKeyboardButton("Перейти в канал", url=f"https://t.me/{ASTRO_CHANNEL_ID.lstrip('@')}")
        )
        subscription_kb.add(
            InlineKeyboardButton("Я подписался", callback_data="check_subscription")
        )
        await message.answer(
            "✅ Готово! Хотите подробный отчёт? Подпишитесь на наш канал про астрологию!",
            reply_markup=subscription_kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error in calculate: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        processing_users.remove(user_id)

@dp.callback_query_handler(lambda c: c.data == "check_subscription")
async def check_subscription(callback_query: types.CallbackQuery):
    user_id = str(callback_query.from_user.id)
    global users
    users = load_users()
    logging.info(f"Checking subscription for user {user_id}. Users loaded: {list(users.keys())}")
    try:
        chat_member = await bot.get_chat_member(ASTRO_CHANNEL_ID, user_id)
        status = chat_member.status
        logging.info(f"User {user_id} subscription status: {status}")

        if status in ["member", "administrator", "creator"]:
            if user_id not in users:
                logging.warning(f"User {user_id} not found in users after subscription check")
                await callback_query.message.edit_text("❗ Сначала сделайте расчёт.")
                await callback_query.answer()
                return
            await callback_query.message.edit_text("✅ Вы подписаны! Формируем подробный отчёт...")
            await send_detailed_parts(callback_query.message)
        else:
            subscription_kb = InlineKeyboardMarkup(row_width=1)
            subscription_kb.add(
                InlineKeyboardButton("Перейти в канал", url=f"https://t.me/{ASTRO_CHANNEL_ID.lstrip('@')}")
            )
            subscription_kb.add(
                InlineKeyboardButton("Я подписался", callback_data="check_subscription")
            )
            await callback_query.message.edit_text(
                "❌ Вы не подписаны на канал. Подпишитесь, чтобы получить подробный отчёт!",
                reply_markup=subscription_kb
            )
    except Exception as e:
        logging.error(f"Error checking subscription for user {user_id}: {e}", exc_info=True)
        await callback_query.message.edit_text("⚠️ Ошибка при проверке подписки. Попробуйте снова.")
    await callback_query.answer()

@dp.message_handler(lambda m: m.text == "📝 Заказать подробный отчёт")
async def request_detailed_report(message: types.Message):
    user_id = str(message.from_user.id)
    global users
    users = load_users()
    logging.info(f"Requesting detailed report for user {user_id}. Users loaded: {list(users.keys())}")
    if user_id not in users:
        logging.warning(f"User {user_id} not found in users for detailed report")
        await message.answer("❗ Сначала сделайте расчёт.")
        return
    subscription_kb = InlineKeyboardMarkup(row_width=1)
    subscription_kb.add(
        InlineKeyboardButton("Перейти в канал", url=f"https://t.me/{ASTRO_CHANNEL_ID.lstrip('@')}")
    )
    subscription_kb.add(
        InlineKeyboardButton("Я подписался", callback_data="check_subscription")
    )
    await message.answer(
        "Чтобы получить подробный отчёт, подпишитесь на наш канал про астрологию!",
        reply_markup=subscription_kb,
        parse_mode="Markdown"
    )

async def send_detailed_parts(message: types.Message):
    user_id = str(message.from_user.id)
    try:
        global users
        users = load_users()
        user_data = users.get(user_id)
        if not user_data:
            logging.warning(f"User data not found for detailed report: {user_id}")
            await message.answer("❗ Сначала сделайте расчёт.")
            return

        first_name = message.from_user.first_name or "Дорогой пользователь"
        date_str = user_data["date_str"]
        time_str = user_data["time_str"]
        city = user_data["city"]
        dt_utc_str = user_data["dt_utc"].strftime("%Y-%m-%d %H:%M:%S")
        lat = user_data["lat"]
        lon = user_data["lon"]

        planet_lines = "\n".join([
            f"{p}: {info['sign']} ({round(info['degree'], 2)}°), дом: {info['house']}"
            for p, info in user_data["planets"].items() if p != "Ascendant"
        ])
        asc_line = f"Ascendant: {user_data['planets']['Ascendant']['sign']}" if "Ascendant" in user_data["planets"] else ""

        header = f"""
Имя: {first_name}
Дата: {date_str}
Время: {time_str}
Город: {city}
UTC: {dt_utc_str}
Широта: {lat}
Долгота: {lon}
Планеты:
{planet_lines}
{asc_line}
"""

        sections = [
            ("Планеты", "Подробно опиши влияние планет на личность, конфликты, дары."),
            ("Дома", "Распиши, как дома влияют на жизнь, особенно в сочетании с планетами."),
            ("Аспекты", "Опиши три значимых аспекта между планетами."),
            ("Асцендент", "Опиши влияние Асцендента на личность и внешний образ."),
            ("Рекомендации", "Дай советы по саморазвитию, любви, карьере.")
        ]

        for title, instruction in sections:
            prompt = f"""
Ты опытный астролог-психолог. Используй данные ниже для анализа.

{header}

Задача: {instruction}
"""

            try:
                res = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.95,
                    max_tokens=3000
                )
                content = res.choices[0].message.content.strip()
                if not content:
                    logging.warning(f"Empty GPT response for section {title}")
                    content = "Не удалось получить анализ."

                pdf = FPDF()
                pdf.add_page()
                pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
                pdf.set_font("DejaVu", size=12)
                for line in content.split("\n"):
                    pdf.multi_cell(0, 10, line)
                    pdf.ln(2)

                filename = f"/tmp/{user_id}_{title}.pdf" if os.getenv("RENDER") else f"{user_id}_{title}.pdf"
                pdf.output(filename)
                with open(filename, "rb") as f:
                    await message.answer_document(f, caption=f"📘 Отчёт: {title}")
                os.remove(filename)
                logging.info(f"Sent report {title} for user {user_id}")
            except Exception as e:
                logging.error(f"Error generating report {title} for user {user_id}: {e}", exc_info=True)
                await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

        logging.info(f"Detailed report completed for user {user_id}")
    except Exception as e:
        logging.error(f"Error in send_detailed_parts for user {user_id}: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка при формировании отчёта: {e}")

async def on_startup(_):
    """Инициализация при запуске бота."""
    await clear_webhook()
    global users
    users = load_users()
    logging.info("Bot started")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)