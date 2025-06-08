from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from flatlib import const
from fpdf import FPDF
from pathlib import Path
from datetime import datetime

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add(KeyboardButton("🚀 Начать расчёт"))

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🔮 Рассчитать", "📄 Скачать PDF")
main_kb.add("💰 Заказать подробный отчёт", "📊 Пример платного отчёта")

users = {}
admin_user_id = 7943520249  # ← твой Telegram ID

def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def example_report(message: types.Message):
    try:
        example_path = "example_paid_astrology_report.pdf"
        if Path(example_path).exists():
            with open(example_path, "rb") as f:
                await message.answer_document(f)
        else:
            await message.answer("Файл с примером пока не загружен.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def send_pdf(message: types.Message):
    user_id = message.from_user.id
    path = f"{user_id}_chart.pdf"
    if Path(path).exists():
        with open(path, "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Сначала рассчитайте карту.")

@dp.message_handler(lambda m: m.text == "💰 Заказать подробный отчёт")
async def order_full_report(message: types.Message):
    if message.from_user.id == admin_user_id:
        path = f"{message.from_user.id}_full.pdf"
        if Path(path).exists():
            with open(path, "rb") as f:
                await message.answer_document(f, caption="Ваш подробный отчёт 💫")
        else:
            await message.answer("Подробный отчет пока не сформирован.")
    else:
        await message.answer("Платный отчёт стоит 299₽. Оплата доступна скоро 💳")

@dp.message_handler()
async def handle_data(message: types.Message):
    try:
        date_str, time_str, city = [x.strip() for x in message.text.split(",")]
        birth_date = datetime.strptime(date_str, "%d.%m.%Y")
        birth_time = datetime.strptime(time_str, "%H:%M").time()

        geo_resp = requests.get(
            f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}"
        ).json()
        coords = geo_resp["results"][0]["geometry"]
        lat, lon = coords["lat"], coords["lng"]

        date = Datetime(birth_date.strftime("%Y/%m/%d"), birth_time.strftime("%H:%M"), '+03:00')
        pos = GeoPos(decimal_to_dms_str(lat), decimal_to_dms_str(lon, is_lat=False))
        chart = Chart(date, pos)

        await message.answer(
            f"📅 Дата: {date_str}, Время: {time_str}, Город: {city}\n🌍 DMS координаты: lat = {decimal_to_dms_str(lat)}, lon = {decimal_to_dms_str(lon, is_lat=False)}\n🪐 Натальная карта построена успешно."
        )

        lines = []
        pdf = FPDF()
        pdf.add_page()
        font_path = "DejaVuSans.ttf"
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)

        for obj in [const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS]:
            planet = chart.get(obj)
            sign = planet.sign
            pos_deg = planet.lon
            text = f"🔍 {obj.title()} в {sign} {pos_deg}"
            await message.answer(text)
            prompt = f"{obj.title()} в знаке {sign}. Расскажи, как это влияет на характер."
            gpt_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )
            answer = gpt_response.choices[0].message.content
            await message.answer(f"📩 GPT: {answer}")
            pdf.multi_cell(0, 10, f"{obj.title()} в {sign}:\n{answer}\n")
            lines.append(f"{obj.title()} в {sign}: {answer}")

        user_pdf_path = f"{message.from_user.id}_chart.pdf"
        pdf.output(user_pdf_path)

        if message.from_user.id == admin_user_id:
            full_path = f"{message.from_user.id}_full.pdf"
            pdf.output(full_path)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
