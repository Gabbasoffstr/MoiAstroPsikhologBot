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

# Initialize bot and configurations
bot = Bot(token=os.getenv("API_TOKEN"))
dp = Dispatcher(bot)
openai.api_key = os.getenv("OPENAI_API_KEY")
logging.basicConfig(level=logging.INFO)

# Keyboards
kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    KeyboardButton("🚀 Начать расчёт"),
    KeyboardButton("📊 Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "🔮 Рассчитать", "📄 Скачать PDF", "📄 Заказать подробный отчёт"
)

# User data storage
users = {}

def decimal_to_dms_str(degree, is_lat=True):
    """Convert decimal coordinates to DMS format string."""
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    """Handle the /start command."""
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Нажми кнопку ниже, чтобы начать расчёт.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    """Begin the calculation process."""
    await message.answer("Введите данные в формате: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    """Send the PDF report if available."""
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        try:
            with open(users[user_id]["pdf"], "rb") as f:
                await message.answer_document(f)
        except FileNotFoundError:
            await message.answer("Файл не найден. Пожалуйста, сделайте новый расчёт.")
    else:
        await message.answer("Сначала рассчитайте карту.")

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    """Calculate the natal chart."""
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        
        if len(parts) != 3:
            await message.answer("⚠️ Неверный формат. Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        
        # Validate date and time
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            await message.answer("⚠️ Неверный формат даты или времени. Используйте ДД.ММ.ГГГГ и ЧЧ:ММ")
            return

        # Get geolocation
        geo_response = requests.get(
            f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={os.getenv('OPENCAGE_API_KEY')}"
        )
        geo = geo_response.json()
        
        if not geo.get("results"):
            await message.answer("❌ Город не найден. Пожалуйста, укажите более конкретное название.")
            return

        lat = geo["results"][0]["geometry"]["lat"]
        lon = geo["results"][0]["geometry"]["lng"]
        lat_str = decimal_to_dms_str(lat, True)
        lon_str = decimal_to_dms_str(lon, False)

        # Get timezone
        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if timezone_str is None:
            await message.answer("❌ Не удалось определить часовой пояс. Пожалуйста, укажите более крупный город рядом.")
            return

        timezone = pytz.timezone(timezone_str)
        dt_input = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        
        try:
            dt_local = timezone.localize(dt_input)
        except pytz.exceptions.AmbiguousTimeError:
            await message.answer("⚠️ Невозможно определить точное время (переход на летнее время). Уточните время.")
            return
            
        dt_utc = dt_local.astimezone(pytz.utc)
        dt = Datetime(dt_utc.strftime("%Y/%m/%d"), dt_utc.strftime("%H:%M"), "+00:00")

        # Create chart
        chart = Chart(dt, GeoPos(lat_str, lon_str))

        # Prepare planet data
        planet_names = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
        summary = []
        for p in planet_names:
            obj = chart.get(p)
            summary.append(f"{p}: {obj.sign}, {round(obj.lon, 2)}°, дом {obj.house}")

        # Generate PDF
        pdf = FPDF()
        pdf.add_page()
        try:
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
        except:
            pdf.set_font("Arial", size=12)  # Fallback font
            
        for line in summary:
            pdf.multi_cell(0, 10, line)
        
        pdf_path = f"user_{user_id}_report.pdf"
        pdf.output(pdf_path)

        # Store user data
        users[user_id] = {
            "pdf": pdf_path,
            "planets": {
                p: {
                    "sign": chart.get(p).sign,
                    "degree": chart.get(p).lon,
                    "house": chart.get(p).house
                } for p in planet_names
            },
            "lat": lat,
            "lon": lon,
            "city": city,
            "date_str": date_str,
            "time_str": time_str,
            "dt_utc": dt_utc
        }

        await message.answer("✅ Натальная карта рассчитана! Теперь можно заказать 📄 подробный отчёт.")
        
    except Exception as e:
        logging.error(f"Error in calculate: {e}")
        await message.answer("❌ Произошла ошибка при расчёте. Пожалуйста, проверьте введённые данные и попробуйте снова.")

@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_detailed_parts(message: types.Message):
    """Generate and send detailed reports."""
    user_id = message.from_user.id
    user_data = users.get(user_id)
    
    if not user_data:
        await message.answer("❗ Сначала сделайте расчёт натальной карты.")
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
        ("Аспекты", "Опиши три наиболее значимых аспекта между планетами."),
        ("Асцендент", "Определи и охарактеризуй Асцендент и его влияние."),
        ("Рекомендации", "Дай практические советы по саморазвитию, отношениям и карьере."),
    ]

    for title, instruction in sections:
        try:
            prompt = f"""
Ты опытный астролог-психолог. Составь подробный анализ на основе этих данных:

{header}

Задача: {instruction}

Будь конкретным, но понятным. Используй профессиональные термины, но объясняй их.
            """

            res = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1500
            )
            content = res.choices[0].message.content.strip()

            pdf = FPDF()
            pdf.add_page()
            try:
                pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
                pdf.set_font("DejaVu", size=12)
            except:
                pdf.set_font("Arial", size=12)
                
            pdf.multi_cell(0, 10, f"Отчёт: {title}\n\n")
            for paragraph in content.split("\n\n"):
                pdf.multi_cell(0, 10, paragraph)
                pdf.ln(5)

            filename = f"detailed_{user_id}_{title}.pdf"
            pdf.output(filename)
            
            with open(filename, "rb") as f:
                await message.answer_document(f, caption=f"📘 {title}")
                
        except Exception as e:
            logging.error(f"Error generating {title}: {e}")
            await message.answer(f"⚠️ Не удалось сгенерировать раздел '{title}'. Пожалуйста, попробуйте позже.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)