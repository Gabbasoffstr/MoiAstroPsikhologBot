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
    KeyboardButton("🚀 Начать расчёт"),
    KeyboardButton("📊 Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "🔮 Рассчитать", "📄 Скачать PDF", "📄 Заказать подробный отчёт"
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

@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
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
                await message.answer_document(f, caption=f"📘 Отчёт: {title}")

        except Exception as e:
            await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨",
        reply_markup=kb,
        parse_mode="Markdown"
    )


if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
