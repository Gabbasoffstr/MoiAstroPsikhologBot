from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from dotenv import load_dotenv
from timezonefinder import TimezoneFinder
import pytz
from datetime import datetime

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# Настройка логирования в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log", mode="a", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    KeyboardButton("🚀 Начать расчёт"),
    KeyboardButton("📊 Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "🔮 Рассчитать", "📄 Скачать PDF", "📄 Заказать подробный отчёт"
)

users = {}
admin_id = 7943520249

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
                if start_lon <= lon < end_lon:
                    return house.id
            else:
                if lon >= start_lon or lon < end_lon:
                    return house.id
        return "?"
    except Exception as e:
        logging.error(f"Error in get_house_manually with longitude {lon}: {e}")
        return "?"

def get_aspects(chart, planet_names):
    """Получение аспектов между планетами."""
    aspects = []
    try:
        for i, p1 in enumerate(planet_names):
            obj1 = chart.get(p1)
            for j in range(i + 1, len(planet_names)):
                p2 = planet_names[j]
                obj2 = chart.get(p2)
                diff = abs(obj1.lon - obj2.lon)
                diff = diff if diff <= 180 else 360 - diff

                if abs(diff - 0) <= 5:
                    aspects.append((p1, p2, diff, "соединение"))
                elif abs(diff - 60) <= 5:
                    aspects.append((p1, p2, diff, "секстиль"))
                elif abs(diff - 90) <= 5:
                    aspects.append((p1, p2, diff, "квадрат"))
                elif abs(diff - 120) <= 5:
                    aspects.append((p1, p2, diff, "тригон"))
                elif abs(diff - 180) <= 5:
                    aspects.append((p1, p2, diff, "оппозиция"))
        return aspects
    except Exception as e:
        logging.error(f"Error in get_aspects: {e}")
        return []

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Нажми кнопку ниже, чтобы начать расчёт.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def send_example_report(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f, caption="📘 Пример платного отчёта")
    except FileNotFoundError:
        await message.answer("⚠️ Пример отчёта не найден. Обратитесь к администратору.")

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        with open(users[user_id]["pdf"], "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Сначала рассчитайте карту.")

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            await message.answer("⚠️ Неверный формат. Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        logging.info(f"Input: {date_str}, {time_str}, {city}")
        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("❌ Город не найден.")
            return

        lat = geo["results"][0]["geometry"]["lat"]
        lon = geo["results"][0]["geometry"]["lng"]
        lat_str = decimal_to_dms_str(lat, True)
        lon_str = decimal_to_dms_str(lon, False)
        logging.info(f"Coordinates: lat={lat_str}, lon={lon_str}")

        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if timezone_str is None:
            await message.answer("❌ Не удалось определить часовой пояс.")
            return
        logging.info(f"Timezone: {timezone_str}")

        timezone = pytz.timezone(timezone_str)
        dt_input = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        dt_local = timezone.localize(dt_input)
        dt_utc = dt_local.astimezone(pytz.utc)
        dt = Datetime(dt_utc.strftime("%Y/%m/%d"), dt_utc.strftime("%H:%M"), "+00:00")
        logging.info(f"UTC Time: {dt_utc}")

        chart = Chart(dt, GeoPos(lat_str, lon_str))  # Без hsys
        logging.info(f"Chart created with houses: {chart.houses}")

        planet_names = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        planet_info = {}
        aspects = get_aspects(chart, planet_names)
        aspects_by_planet = {p: [] for p in planet_names}
        for p1, p2, diff, aspect_name in aspects:
            aspects_by_planet[p1].append(f"{p1} {aspect_name} {p2} ({round(diff, 1)}°)")
            aspects_by_planet[p2].append(f"{p2} {aspect_name} {p1} ({round(diff, 1)}°)")
        logging.info(f"Aspects calculated: {aspects}")

        for p in planet_names:
            obj = chart.get(p)
            sign, deg = obj.sign, obj.lon
            house = get_house_manually(chart, deg)
            logging.info(f"Processing planet: {p}, Sign: {sign}, Deg: {deg}, House: {house}")

            # GPT интерпретация
            prompt = f"{p} в знаке {sign}, дом {house}, долгота {deg:.2f}. Дай краткую астрологическую интерпретацию."
            try:
                res = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=500
                )
                reply = res.choices[0].message.content.strip()
            except Exception as e:
                logging.error(f"Error in GPT interpretation for {p}: {e}")
                reply = "Не удалось получить интерпретацию."

            await message.answer(f"🔍 {p} в {sign}, дом {house}")
            await message.answer(f"📩 {reply}")
            aspect_text = "\n".join([f"• {a}" for a in aspects_by_planet[p]]) if aspects_by_planet[p] else "• Нет точных аспектов"
            await message.answer(f"📐 Аспекты:\n{aspect_text}")

            summary.append(f"{p} в {sign}, дом {house}:\n📐 Аспекты:\n{aspect_text}\n📩 {reply}")
            planet_info[p] = {
                "sign": sign,
                "degree": deg,
                "house": house
            }

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        for line in summary:
            pdf.multi_cell(0, 10, line)
        pdf_path = f"user_{user_id}_report.pdf"
        pdf.output(pdf_path)
        logging.info(f"PDF created: {pdf_path}")

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
        logging.info(f"User data saved: {users[user_id]}")

        await message.answer("✅ Готово! Теперь можно заказать 📄 подробный отчёт.")
    except Exception as e:
        logging.error(f"Error in calculate: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_detailed_parts(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)
    if not user_data:
        await message.answer("❗ Сначала сделайте расчёт.")
        return

    first_name = message.from_user.first_name or "Дорогой друг"
    date_str = user_data["date_str"]
    time_str = user_data["time_str"]
    city = user_data["city"]
    dt_utc_str = user_data["dt_utc"].strftime("%Y-%m-%d %H:%M")
    lat = user_data["lat"]
    lon = user_data["lon"]

    planet_lines = "\n".join([
        f"{p}: {info['sign']} ({round(info['degree'], 2)}°), дом: {info['house']}"
        for p, info in user_data["planets"].items()
    ])

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
"""

    sections = [
        ("Планеты", "Подробно опиши влияние планет на личность, конфликты, дары."),
        ("Дома", "Распиши, как дома влияют на жизнь, особенно в сочетании с планетами."),
        ("Аспекты", "Опиши три значимых аспекта между планетами."),
        ("Асцендент", "Определи и охарактеризуй Асцендент."),
        ("Рекомендации", "Дай советы по саморазвитию, любви, карьере."),
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

            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            for paragraph in content.split("\n\n"):
                for line in paragraph.split("\n"):
                    pdf.multi_cell(0, 10, line)
                pdf.ln(3)

            filename = f"{user_id}_{title}.pdf"
            pdf.output(filename)
            with open(filename, "rb") as f:
                await message.answer_document(f, caption=f"📘 Отчёт: {title}")
        except Exception as e:
            logging.error(f"Error generating report {title}: {e}")
            await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)