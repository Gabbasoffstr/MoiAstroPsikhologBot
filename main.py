from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from dotenv import load_dotenv
from collections import defaultdict
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
logging.basicConfig(level=logging.INFO)

kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    KeyboardButton("\U0001F680 Начать расчёт"),
    KeyboardButton("\U0001F4CA Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "\U0001F52E Рассчитать", "\U0001F4C4 Скачать PDF", "\U0001F4C4 Заказать подробный отчёт"
)

users = {}
report_usage = defaultdict(int)
admin_id = 7943520249
channel_id = -1002581118151

def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "\U0001F44B Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "\U0001F680 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "\U0001F4CA Пример платного отчёта")
async def example_pdf(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f)
    except FileNotFoundError:
        await message.answer("⚠️ Пример отчёта пока не загружен.")

@dp.message_handler(lambda m: m.text == "\U0001F52E Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            await message.answer("⚠️ Неверный формат. Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("❌ Город не найден.")
            return

        lat = geo["results"][0]["geometry"]["lat"]
        lon = geo["results"][0]["geometry"]["lng"]
        lat_str = decimal_to_dms_str(lat, True)
        lon_str = decimal_to_dms_str(lon, False)

        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if timezone_str is None:
            await message.answer("❌ Не удалось определить часовой пояс.")
            return

        timezone = pytz.timezone(timezone_str)
        dt_input = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        dt_local = timezone.localize(dt_input)
        dt_utc = dt_local.astimezone(pytz.utc)
        dt = Datetime(dt_utc.strftime("%Y/%m/%d"), dt_utc.strftime("%H:%M"), "+00:00")

        chart = Chart(dt, GeoPos(lat_str, lon_str))
        await message.answer("\U0001FA90 Натальная карта построена.")

        planets = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        for p in planets:
            obj = chart.get(p)
            sign, deg = obj.sign, obj.lon
            summary.append(f"{p}: {sign} ({round(deg, 2)})")
            await message.answer(f"🔍 {p} в {sign}, {round(deg, 2)}°")

        users[user_id] = {
            "planets": {p: {"sign": chart.get(p).sign, "degree": chart.get(p).lon} for p in planets},
            "date_str": date_str,
            "time_str": time_str,
            "city": city,
            "lat": lat,
            "lon": lon,
            "dt_utc": dt_utc
        }

        await message.answer("✅ Готово. Нажмите \U0001F4C4 Заказать подробный отчёт")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "\U0001F4C4 Скачать PDF")
async def download_pdf(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)
    if user_data and os.path.exists(user_data.get("pdf", "")):
        with open(user_data["pdf"], "rb") as f:
            await message.answer_document(f, caption="📄 Ваш отчёт")
    else:
        await message.answer("❗ Сначала рассчитайте карту.")

@dp.message_handler(lambda m: m.text == "\U0001F4C4 Заказать подробный отчёт")
async def send_detailed_parts(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)
    if not user_data:
        await message.answer("❗ Сначала сделайте расчёт.")
        return

    first_name = message.from_user.first_name or "Дорогой друг"
    date_str = user_data.get("date_str", "Неизвестно")
    time_str = user_data.get("time_str", "Неизвестно")
    city = user_data.get("city", "Неизвестно")
    dt_utc = user_data.get("dt_utc")
    lat = user_data.get("lat")
    lon = user_data.get("lon")
    dt_utc_str = dt_utc.strftime("%Y-%m-%d %H:%M") if dt_utc else "Неизвестно"

    planet_lines = "\n".join([
        f"{planet}: {info['sign']} ({round(info['degree'], 2)})"
        for planet, info in user_data.get("planets", {}).items()
    ])

    header = f"""
Имя: {first_name}
Дата: {date_str}
Время: {time_str}
Город: {city}
UTC: {dt_utc_str}
Широта: {lat}
Долгота: {lon}
"""

    sections = [
        ("Планеты", "Опиши подробно каждую из планет и её влияние на характер и внутренние конфликты."),
        ("Дома", "Опиши, как дома проявляются в жизни человека и как они взаимодействуют с планетами."),
        ("Аспекты", "Придумай 3 значимых аспекта между планетами и раскрой их смысл."),
        ("Асцендент", "Определи Асцендент и опиши, как он влияет на личность и восприятие мира."),
        ("Рекомендации", "Дай советы по саморазвитию, карьере, отношениям. Будь человечным и доброжелательным."),
    ]

    for title, instruction in sections:
        prompt = f"""
Ты опытный астролог-психолог. Используй данные ниже для анализа.
{header}
Планеты:
{planet_lines}

Задача: {instruction}
        """
        try:
            res = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.95,
                max_tokens=2000
            )
            content = res.choices[0].message.content.strip()

            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            pdf.set_auto_page_break(auto=True, margin=15)

            for paragraph in content.split("\n\n"):
                for line in paragraph.split("\n"):
                    pdf.multi_cell(0, 10, line)
                pdf.ln(3)

            filename = f"{user_id}_{title}.pdf"
            pdf.output(filename)
            with open(filename, "rb") as f:
                await message.answer_document(f, caption=f"\U0001F4D8 Отчёт: {title}")

        except Exception as e:
            await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
