from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from dotenv import load_dotenv

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
    "🔮 Рассчитать", "📄 Скачать PDF", "💰 Купить полный разбор"
)

users = {}
admin_id = 7943520249  # твой Telegram ID


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


@dp.message_handler(lambda m: m.text == "💰 Купить полный разбор")
async def buy(message: types.Message):
    btn = InlineKeyboardMarkup().add(InlineKeyboardButton("Оплатить 199₽", url="https://your-site.com/pay"))
    await message.answer(
        "📎 Мы уже подготовили для тебя платный анализ — карьера, финансы, любовь, аспекты. Оплати и получи PDF!",
        reply_markup=btn
    )


@dp.message_handler(lambda m: m.text == "📄 Скачать PDF")
async def pdf(message: types.Message):
    user_id = message.from_user.id
    if user_id in users and "pdf" in users[user_id]:
        if user_id == admin_id or users[user_id].get("paid"):
            with open(users[user_id]["pdf"], "rb") as f:
                await message.answer_document(f)
        else:
            await message.answer("🔒 Платный отчёт доступен после оплаты.")
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
            sign = obj.sign
            deg = obj.lon
            await message.answer(f"🔍 {p} в {sign} {deg}")
            prompt = f"{p} в знаке {sign}, долгота {deg}. Дай астрологическую интерпретацию."
            res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
            gpt_reply = res.choices[0].message.content.strip()
            await message.answer(f"📩 GPT: {gpt_reply}")
            summary.append(f"{p}: {gpt_reply}\n")

        # Генерация PDF с поддержкой кириллицы
        pdf = FPDF()
        pdf.add_page()
        font_path = "DejaVuSans.ttf"
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=12)
        for s in summary:
            pdf.multi_cell(0, 10, s)
        pdf_path = f"user_{user_id}_report.pdf"
        pdf.output(pdf_path)

        users[user_id] = {"pdf": pdf_path, "paid": (user_id == admin_id)}

        await message.answer("✅ Бесплатная часть готова. Хочешь полный разбор — нажми 💰 Купить полный разбор")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_paid_report(message: types.Message):
    user_id = str(message.from_user.id)
    birth_data = users.get(message.from_user.id, {})
    if not birth_data.get("planets"):
        await message.answer("❌ Сначала сделай бесплатный расчёт.")
        return

    await message.answer("🧠 Генерирую максимально подробный отчёт, подождите...")

    try:
        prompt = (
            "Составь очень подробный астропсихологический анализ личности по данным натальной карты. "
            "Укажи и распиши каждый пункт:\n"
            "1. Общий характер\n"
            "2. Мышление\n"
            "3. Эмоции\n"
            "4. Любовь\n"
            "5. Энергия и действия\n"
            "6. Финансовый потенциал\n"
            "7. Подходящие профессии\n"
            "8. Карьерный потенциал\n"
            "9. Стиль общения\n"
            "10. Советы для развития\n"
            "11. Врожденные таланты\n"
            "12. Эмоциональные потребности\n"
            "13. Кармические уроки\n"
            "14. Психологические особенности\n"
            "15. Семейная жизнь\n"
            "16. Уровень духовности\n"
            "17. Тенденции в личной жизни\n\n"
            "Вот данные планет:\n"
        )
        for planet, info in birth_data["planets"].items():
            prompt += f"{planet}: {info['sign']} ({info['degree']})\n"

        gpt_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2048
        )
        full_text = gpt_response.choices[0].message.content.strip()

        # PDF генерация
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
        await message.answer(f"❌ Ошибка при генерации отчёта: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
