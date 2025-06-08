from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

# Кнопки горизонтально
main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
main_kb.add("🔮 Рассчитать", "📄 Скачать PDF", "📊 Пример платного отчёта", "💰 Купить полный разбор")

users = {}

def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🚀 Начать расчёт"))
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта* — бот, который расскажет, что заложено в твоей натальной карте.\n\nНажми кнопку ниже, чтобы начать 🔮",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "💰 Купить полный разбор")
async def buy(message: types.Message):
    btn = InlineKeyboardMarkup().add(InlineKeyboardButton("Оплатить 199₽", url="https://your-site.com/pay"))
    await message.answer("💳 Перейди по ссылке для оплаты полного PDF 🔐", reply_markup=btn)

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        with open(users[user_id]["pdf"], "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Сначала рассчитайте натальную карту.")

@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def show_example(message: types.Message):
    path = "example_paid_astrology_report.pdf"
    if os.path.exists(path):
        with open(path, "rb") as f:
            await message.answer_document(f, caption="📄 Пример платного отчёта")
    else:
        await message.answer("Файл с примером пока не загружен.")

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            await message.answer("⚠️ Неверный формат. Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        await message.answer(f"📅 Дата: {date_str}, Время: {time_str}, Город: {city}")

        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("❌ Город не найден.")
            return

        lat = geo["results"][0]["geometry"]["lat"]
        lon = geo["results"][0]["geometry"]["lng"]

        lat_str = decimal_to_dms_str(lat, is_lat=True)
        lon_str = decimal_to_dms_str(lon, is_lat=False)

        await message.answer(f"🌍 DMS координаты: lat = {lat_str}, lon = {lon_str}")

        dt = Datetime(f"{date_str[6:]}/{date_str[3:5]}/{date_str[0:2]}", time_str, "+03:00")
        chart = Chart(dt, GeoPos(lat_str, lon_str))
        await message.answer("🪐 Натальная карта построена успешно.")

        planets = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        for p in planets:
            try:
                obj = chart.get(p)
                await message.answer(f"🔍 {p} в {obj.sign} {obj.lon}")
                prompt = f"{p} в знаке {obj.sign}. Астрологическая интерпретация?"
                res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
                reply = res.choices[0].message.content.strip()
                await message.answer(f"📩 GPT: {reply}")
                summary.append(f"{p}: {reply}\n")
            except Exception as ex:
                await message.answer(f"⚠️ Ошибка при обработке {p}: {ex}")

        # PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        for s in summary:
            pdf.multi_cell(0, 10, s)

        filename = f"{user_id}_chart.pdf"
        pdf.output(filename)
        users[user_id] = {"pdf": filename}

        await message.answer("✅ Бесплатный отчёт готов! 📄 Вы можете скачать его или 👀 посмотреть, что входит в платный отчёт:")
        await message.answer("👇 Выберите действие:", reply_markup=main_kb)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
