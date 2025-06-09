from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging, os, requests, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

# Кнопки
kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    KeyboardButton("🚀 Начать расчёт"),
    KeyboardButton("📊 Пример платного отчёта")
)

main_kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1).add(
    "🔮 Рассчитать", "📄 Скачать PDF", "📄 Заказать подробный отчёт"
)

# Пользователи и лимит
users = {}
report_usage = defaultdict(int)
admin_id = 7943520249  # замени на свой Telegram ID
channel_id = -1002581118151    # закрытый канал

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
        "👋 Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# Начало
@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

# Пример
@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def example_pdf(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f)
    except:
        await message.answer("Файл с примером пока не загружен.")

# Скачать PDF
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

# Бесплатный расчёт
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

        dt = Datetime(f"{date_str[6:]}/{date_str[3:5]}/{date_str[:2]}", time_str, "+03:00")
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

        users[user_id] = {"pdf": pdf_path, "planets": {p: {"sign": chart.get(p).sign, "degree": chart.get(p).lon} for p in planets}, "paid": (user_id == admin_id)}

        await message.answer("✅ Готово. Хочешь подробный отчёт? Нажми 📄 Заказать подробный отчёт")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Подробный отчёт (платный)
@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_paid_report(message: types.Message):
    user_id = message.from_user.id
    max_uses = 2

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        if member.status not in ["member", "administrator", "creator"]:
            await message.answer(
                f"🔒 Чтобы получить полный разбор, подпишитесь на {channel_username}",
                parse_mode="Markdown"
            )
            return

        if report_usage[user_id] >= max_uses:
            await message.answer("⛔️ Вы уже использовали 2 платных разбора.")
            return

        planets = users.get(user_id, {}).get("planets", {})
        if not planets:
            await message.answer("❗ Сначала сделайте бесплатный расчёт.")
            return

        await message.answer("🧠 Генерирую подробный отчёт...")

        prompt = (
    "Составь максимально подробный астропсихологический разбор личности по натальной карте. "
    "Используй реальные астрологические знания. Учти следующее:\n\n"

    "1. Для каждой планеты (Солнце, Луна, Меркурий, Венера, Марс, Юпитер, Сатурн, Уран, Нептун, Плутон) укажи:\n"
    "- знак, в котором она находится, и его значение;\n"
    "- дом, в котором она находится, и его влияние на сферу жизни;\n"
    "- пояснение, как это проявляется в реальной жизни человека;\n"
    "- практические советы и рекомендации по самореализации в этих качествах.\n\n"

    "2. Проанализируй каждый из 12 домов:\n"
    "- что означает этот дом;\n"
    "- какие планеты в нём расположены и что это даёт;\n"
    "- выводы о поведении человека в соответствующих сферах (семья, карьера, любовь и т.д.).\n\n"

    "3. Разбери основные аспекты между планетами:\n"
    "- перечисли ключевые аспекты (трины, квадраты, оппозиции и т.п.);\n"
    "- объясни их значение, внутренние конфликты или дары;\n"
    "- как это может влиять на личность и судьбу.\n\n"

    "4. Определи и опиши Асцендент:\n"
    "- в каком он знаке;\n"
    "- как влияет на внешность, стиль, впечатление, поведение;\n"
    "- советы по социализации и самопрезентации.\n\n"

    "5. В финале: дай советы по развитию, сильные и слабые стороны личности, что стоит принять, что развивать, какие профессии подходят.\n\n"
    "Отчёт должен быть профессиональным, содержательным и полезным. Используй живой язык, делай акценты и давай конкретные советы."
)

        for planet, info in planets.items():
            prompt += f"{planet}: {info['sign']} ({round(info['degree'], 2)})\n"

        res = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=2048
        )
        full_text = res.choices[0].message.content.strip()

        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        for line in full_text.split("\n"):
            pdf.multi_cell(0, 10, line)
        paid_path = f"paid_{user_id}.pdf"
        pdf.output(paid_path)

        with open(paid_path, "rb") as f:
            await message.answer_document(f, caption="📄 Ваш подробный отчёт")

        report_usage[user_id] += 1

    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {e}")

# Запуск
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
