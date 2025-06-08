from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging, os, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from flatlib import const
from fpdf import FPDF
from pathlib import Path
from datetime import datetime

# 🔐 Настройки API
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# 🔧 Настройки логгера и бота
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# 📱 Клавиатура
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🔮 Рассчитать", "📄 Скачать PDF")
main_kb.add("📄 Заказать подробный отчёт", "📊 Пример платного отчёта")

# 📦 Данные пользователей
users = {}

# 🌐 Шаблон координат
def decimal_to_dms_str(degree, is_lat=True):
    d = int(abs(degree))
    m = int((abs(degree) - d) * 60)
    suffix = 'n' if is_lat and degree >= 0 else 's' if is_lat else 'e' if degree >= 0 else 'w'
    return f"{d}{suffix}{str(m).zfill(2)}"

# ▶️ /start
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("👋 Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨", reply_markup=main_kb, parse_mode="Markdown")

# 🔮 Рассчитать
@dp.message_handler(lambda m: m.text == "🔮 Рассчитать")
async def ask_birth_data(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город (пример: 06.10.1985, 19:15, Стерлитамак)")

# Обработка ввода даты
@dp.message_handler(lambda m: "," in m.text)
async def process_data(message: types.Message):
    try:
        user_id = str(message.from_user.id)
        date_str, time_str, city = [x.strip() for x in message.text.split(",", 2)]
        date_obj = datetime.strptime(date_str.replace("-", ".").replace("/", "."), "%d.%m.%Y")
        dt_str = date_obj.strftime("%Y/%m/%d")
        dt = Datetime(dt_str, time_str, "+03:00")
        lat, lon = 53.63, 55.95  # временно фиксированные координаты
        pos = GeoPos(decimal_to_dms_str(lat), decimal_to_dms_str(lon, is_lat=False))
        chart = Chart(dt, pos)

        planets = {}
        for obj in [const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS]:
            p = chart.get(obj)
            planets[obj] = {"sign": p.sign, "degree": p.lon}

        users[user_id] = {"chart": chart, "planets": planets}

        planet_descriptions = []
        for name, info in planets.items():
            planet_descriptions.append(f"{name.title()} в {info['sign']} ({round(info['degree'], 2)})")

        await message.answer("🪐 Натальная карта:\n" + "\n".join(planet_descriptions))

        # Сохраняем PDF краткий
        pdf = FPDF()
        pdf.add_page()
        font_path = "DejaVuSans.ttf"
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
        for line in planet_descriptions:
            pdf.cell(0, 10, txt=line, ln=True)
        path = f"chart_{user_id}.pdf"
        pdf.output(path)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# 📄 Скачать PDF
@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def send_pdf(message: types.Message):
    user_id = str(message.from_user.id)
    path = f"chart_{user_id}.pdf"
    if Path(path).exists():
        with open(path, "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Файл ещё не создан. Сначала сделай расчёт.")

# 📊 Пример платного отчёта
@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def example_report(message: types.Message):
    example_path = "example_paid_astrology_report.pdf"
    if Path(example_path).exists():
        with open(example_path, "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Файл с примером пока не загружен.")

# 📄 Заказать подробный отчёт
@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_paid_report(message: types.Message):
    user_id = str(message.from_user.id)
    birth_data = users.get(user_id, {})
    if not birth_data.get("planets"):
        await message.answer("❌ Сначала сделай бесплатный расчёт.")
        return

    await message.answer("🧠 Генерирую подробный отчёт, подождите...")

    try:
        prompt = (
            "Составь полный и подробный астропсихологический анализ личности по этим данным:\n"
            "Опиши: черты характера, мышление, эмоции, любовь, действия.\n"
            "Добавь: примеры профессий, финансовый потенциал, стиль общения, советы для развития.\n"
        )
        for planet, info in birth_data["planets"].items():
            prompt += f"{planet}: {info['sign']} ({info['degree']})\n"

        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        full_text = gpt_response.choices[0].message.content.strip()

        pdf = FPDF()
        pdf.add_page()
        font_path = "DejaVuSans.ttf"
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
        for line in full_text.split("\n"):
            pdf.multi_cell(0, 10, line)

        paid_path = f"paid_{user_id}.pdf"
        pdf.output(paid_path)

        with open(paid_path, "rb") as f:
            await message.answer_document(f, caption="📄 Ваш подробный отчёт")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ▶️ Старт бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
