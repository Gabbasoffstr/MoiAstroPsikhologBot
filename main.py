from aiogram import Bot, Dispatcher, types
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
async def example_pdf(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f)
    except:
        await message.answer("Файл с примером пока не загружен.")

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        if user_id == admin_id or users[user_id].get("paid"):
            with open(users[user_id]["pdf"], "rb") as f:
                await message.answer_document(f)
        else:
            await message.answer("🔐 Платный отчёт доступен после оплаты.")
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
            await message.answer("❌ Не удалось определить часовой пояс. Попробуйте другой город.")
            return

        timezone = pytz.timezone(timezone_str)
        dt_input = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
        dt_local = timezone.localize(dt_input)
        dt_utc = dt_local.astimezone(pytz.utc)
        dt = Datetime(dt_utc.strftime("%Y/%m/%d"), dt_utc.strftime("%H:%M"), "+00:00")

        chart = Chart(dt, GeoPos(lat_str, lon_str))
        await message.answer("🪐 Натальная карта построена.")

        planets = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        for p in planets:
            obj = chart.get(p)
            sign, deg = obj.sign, obj.lon
            prompt = f"{p} в знаке {sign}, долгота {deg}. Дай астрологическую интерпретацию."
            res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
            reply = res.choices[0].message.content.strip()
            summary.append(f"{p}: {reply}\n")
            await message.answer(f"🔍 {p} в {sign} — 📩 {reply}")

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
            "planets": {p: {"sign": chart.get(p).sign, "degree": chart.get(p).lon} for p in planets},
            "paid": (user_id == admin_id),
            "date_str": date_str,
            "time_str": time_str,
            "city": city,
            "dt_utc": dt_utc
        }

        await message.answer("✅ Готово. Хочешь подробный отчёт? Нажми 📄 Заказать подробный отчёт")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_paid_report(message: types.Message):
    user_id = message.from_user.id
    max_uses = 4

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status not in ["member", "administrator", "creator"]:
            await message.answer("🔒 Чтобы получить полный разбор, подпишитесь на закрытый канал.", parse_mode="Markdown")
            return

        if report_usage[user_id] >= max_uses:
            await message.answer("⛔️ Вы уже использовали 2 платных разбора.")
            return

        planets = users.get(user_id, {}).get("planets", {})
        if not planets:
            await message.answer("❗ Сначала сделайте бесплатный расчёт.")
            return

        await message.answer("🧠 Генерирую подробный отчёт в 5 частях... Подождите 1–2 минуты.")

        planet_lines = "".join([f"{planet}: {info['sign']} ({round(info['degree'], 2)})\n" for planet, info in planets.items()])
        first_name = message.from_user.first_name or "Дорогой друг"
        user_data = users.get(user_id, {})
        date_str = user_data.get("date_str", "Неизвестно")
        time_str = user_data.get("time_str", "Неизвестно")
        city = user_data.get("city", "Неизвестно")
        dt_utc = user_data.get("dt_utc")
        dt_utc_str = dt_utc.strftime("%Y-%m-%d %H:%M") if dt_utc else "Неизвестно"

        prompts = [
            "Подробно опиши, как каждая планета влияет на личность. 1-2 абзаца на каждую. Пиши красиво и с примерами.",
            "Расскажи, как дома влияют на проявление этих планет. Приводи метафоры и жизненные ситуации.",
            "Разбери 3 ключевых аспекта между планетами. Объясни, как они влияют на конфликты и таланты.",
            "Определи асцендент по данным и объясни, как он влияет на поведение, внешность и стиль общения.",
            "Дай персональные советы по саморазвитию, любви, карьере. Напиши как личную рекомендацию астролога."
        ]

        for i, prompt in enumerate(prompts, start=1):
            full_prompt = f"""
Ты опытный астропсихолог. Клиент — {first_name}, родился(ась): {date_str}, {time_str}, город: {city}, UTC: {dt_utc_str}.
Вот его положения планет:
{planet_lines}

{prompt}
"""
            res = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.95,
                max_tokens=1800
            )
            text = res.choices[0].message.content.strip()

            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            pdf.set_auto_page_break(auto=True, margin=15)
            for paragraph in text.split("\n\n"):
                for line in paragraph.split("\n"):
                    pdf.multi_cell(0, 10, line)
                pdf.ln(4)
            pdf_path = f"user_{user_id}_part{i}.pdf"
            pdf.output(pdf_path)

            with open(pdf_path, "rb") as f:
                await message.answer_document(f, caption=f"📄 Часть {i} из 5")

        report_usage[user_id] += 1

    except Exception as e:
        await message.answer(f"⚠️ Ошибка при генерации отчёта: {e}")

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
