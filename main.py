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

# Кнопки
main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
main_kb.add(
    KeyboardButton("🔮 Рассчитать"),
    KeyboardButton("📄 Скачать PDF"),
    KeyboardButton("💰 Купить полный разбор"),
    KeyboardButton("📊 Пример платного отчёта")
)

users = {}

def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Этот бот рассчитает и объяснит, что заложено в твоей натальной карте.\n\nНажми кнопку ниже, чтобы начать 🔮",
        reply_markup=main_kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            await message.answer("⚠️ Введите: ДД.ММ.ГГГГ, ЧЧ:ММ, Город")
            return

        date_str, time_str, city = parts
        await message.answer(f"📅 Дата: {date_str}, Время: {time_str}, Город: {city}")

        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("❌ Город не найден. Попробуйте другой.")
            return

        lat = geo["results"][0]["geometry"].get("lat")
        lon = geo["results"][0]["geometry"].get("lng")

        lat_str = decimal_to_dms_str(lat, is_lat=True)
        lon_str = decimal_to_dms_str(lon, is_lat=False)
        await message.answer(f"🌍 DMS координаты: lat = {lat_str}, lon = {lon_str}")

        dt = Datetime(f"{date_str[6:10]}/{date_str[3:5]}/{date_str[0:2]}", time_str, "+03:00")
        chart = Chart(dt, GeoPos(lat_str, lon_str))
        await message.answer("🪐 Натальная карта построена успешно.")

        planets = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []

        for p in planets:
            obj = chart.get(p)
            await message.answer(f"🔍 {p} в {obj.sign} {obj.lon}")
            try:
                prompt = f"{p} в знаке {obj.sign}, долгота {obj.lon}. Астрологическая расшифровка?"
                res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
                gpt_reply = res.choices[0].message.content.strip()
                await message.answer(f"📩 GPT: {gpt_reply}")
                summary.append(f"{p}: {gpt_reply}\n")
            except Exception as e:
                await message.answer(f"⚠️ Ошибка при обработке {p}: {e}")

        # Генерация PDF с поддержкой кириллицы
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        for s in summary:
            pdf.multi_cell(0, 10, s)
        pdf_path = f"{user_id}_chart.pdf"
        pdf.output(pdf_path)

        users[user_id] = {"pdf": pdf_path}
        await message.answer("✅ Бесплатный отчёт готов! Вы можете:\n- 📄 Скачать PDF\n- 💰 Получить полный разбор\n- 📊 Посмотреть пример платного отчёта", reply_markup=main_kb)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def send_pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and os.path.exists(users[user_id]["pdf"]):
        with open(users[user_id]["pdf"], "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("⚠️ Сначала рассчитайте натальную карту.")

@dp.message_handler(lambda m: m.text == "💰 Купить полный разбор")
async def buy(message: types.Message):
    btn = InlineKeyboardMarkup().add(InlineKeyboardButton("Оплатить 199₽", url="https://your-site.com/pay"))
    await message.answer("🔒 Получите полный платный отчёт — это глубокий анализ всех аспектов, совместимость, рекомендации, финансы и карьера.\n\n👉 Нажмите кнопку ниже, чтобы оплатить:", reply_markup=btn)

@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def show_example(message: types.Message):
    await message.answer(
        "📊 *Пример платного отчёта:*\n\n"
        "🌞 Солнце в Весах — стремление к гармонии, дипломатичность, любовь к красоте и балансу.\n"
        "🌝 Луна в Раке — эмоциональность, потребность в заботе, чувствительность.\n"
        "☿ Меркурий в Весах — логичность, дипломатия, стремление к честности.\n"
        "♀ Венера в Деве — перфекционизм в любви, анализ чувств.\n"
        "♂ Марс в Деве — целеустремлённость, внутренняя дисциплина.\n"
        "♃ Юпитер в Водолее — прогрессивное мышление, гуманизм.\n"
        "♄ Сатурн в Стрельце — философская строгость, тяга к знанию.\n"
        "❤️ Любовные аспекты: Венера секстиль Луна — эмоциональное согласие в отношениях.\n"
        "🎯 Кармическая задача: развить уверенность и научиться договариваться.",
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
