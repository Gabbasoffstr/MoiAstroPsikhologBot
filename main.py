from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF

# Настройки
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

# Клавиатуры
kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("🚀 Начать расчёт"))
main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add("🔮 Рассчитать", "📄 Скачать PDF", "💰 Купить полный разбор")
users = {}

# Преобразование координат
def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

# Старт
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Мой АстроПсихолог* — бот, который расскажет, что заложено в твоей натальной карте.\n\nНажми кнопку ниже, чтобы начать 🔮",
        reply_markup=kb, parse_mode="Markdown"
    )

# Начать расчёт
@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

# Оплата
@dp.message_handler(lambda m: m.text == "💰 Купить полный разбор")
async def buy(message: types.Message):
    btn = InlineKeyboardMarkup().add(InlineKeyboardButton("Оплатить 199₽", url="https://your-site.com/pay"))
    await message.answer("Перейди по ссылке для оплаты полного PDF 🔐", reply_markup=btn)

# Скачать PDF
@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        with open(users[user_id]["pdf"], "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Сначала рассчитайте карту.")

# Расчёт
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

        # Получение координат
        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("❌ Город не найден.")
            return

        lat = geo["results"][0]["geometry"].get("lat")
        lon = geo["results"][0]["geometry"].get("lng")
        if lat is None or lon is None:
            await message.answer("❌ Координаты не распознаны.")
            return

        lat_str = decimal_to_dms_str(lat, is_lat=True)
        lon_str = decimal_to_dms_str(lon, is_lat=False)

        await message.answer(f"🌍 DMS координаты: lat = {lat_str}, lon = {lon_str}")

        # Натальная карта
        dt = Datetime(f"{date_str[6:10]}/{date_str[3:5]}/{date_str[0:2]}", time_str, "+03:00")
        chart = Chart(dt, GeoPos(lat_str, lon_str))
        await message.answer("🪐 Натальная карта построена успешно.")

        planets = [("Sun", "SUN"), ("Moon", "MOON"), ("Mercury", "MERCURY"), ("Venus", "VENUS"), ("Mars", "MARS")]
        summary = []

        for name, key in planets:
            try:
                obj = chart.get(key)
                await message.answer(f"🔍 {name} в {obj.sign} {obj.lon}")
                prompt = f"{name} в знаке {obj.sign}. Астрологическая расшифровка?"
                res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
                gpt_reply = res.choices[0].message.content.strip()
                await message.answer(f"📩 GPT: {gpt_reply}")
                summary.append(f"{name}: {gpt_reply}\n")
            except Exception as e:
                await message.answer(f"⚠️ Ошибка при обработке {name}: {e}")

        if not summary:
            await message.answer("⚠️ Не удалось построить описание.")
            return

        # PDF генерация
        pdf = FPDF()
        pdf.add_page()

        font_path = "DejaVuSans.ttf"
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)

        for s in summary:
            pdf.multi_cell(0, 10, s)

        # Сохранение
        pdf_dir = "generated"
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{user_id}_chart.pdf")
        pdf.output(pdf_path)

        users[user_id] = {"pdf": pdf_path}
        await message.answer("✅ Готово! Нажмите 📄 Скачать PDF")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Запуск
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
