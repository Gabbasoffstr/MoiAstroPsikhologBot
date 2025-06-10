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
logging.basicConfig(level=logging.INFO)

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

        planet_names = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        planet_info = {}
    aspects = get_aspects(chart, planet_names)
aspects_by_planet = {p: [] for p in planet_names}
for p1, p2, diff, aspect_name in aspects:
    aspects_by_planet[p1].append(f"{p1} {aspect_name} {p2} ({round(diff, 1)}°)")
    aspects_by_planet[p2].append(f"{p2} {aspect_name} {p1} ({round(diff, 1)}°)")
    def get_aspects(chart, planet_names):
except Exception as e:
    await message.answer(f"❌ Ошибка при расчёте аспектов: {e}")
    aspects = []

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

        for p in planet_names:
            obj = chart.get(p)
            sign, deg = obj.sign, obj.lon
            try:
                house = chart.houses.getObjectHouse(obj).num()
            except:
                house = "?"
            await message.answer(f"🔍 {p} в {sign}, дом {house}")

            # GPT интерпретация
            prompt = f"{p} в знаке {sign}, дом {house}, долгота {deg}. Дай краткую астрологическую интерпретацию."
            res = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            reply = res.choices[0].message.content.strip()
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

        await message.answer("✅ Готово! Теперь можно заказать 📄 подробный отчёт.")
    except Exception as e:
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
            await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

def get_chart_aspects(chart, planet_names):
    aspect_list = []
    for i, p1 in enumerate(planet_names):
        for p2 in planet_names[i + 1:]:
            asp = aspects.getAspect(chart.get(p1), chart.get(p2))
            if asp and asp.type in [
                AspectTypes.CONJUNCTION,
                AspectTypes.OPPOSITION,
                AspectTypes.TRINE,
                AspectTypes.SQUARE,
                AspectTypes.SEXTILE
            ]:
                aspect_list.append(f"{p1} {asp.type} {p2} ({round(asp.orb, 2)}°)")
    return aspect_list

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)