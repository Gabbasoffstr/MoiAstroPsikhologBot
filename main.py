from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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
        await message.answer("\u0424\u0430\u0439\u043b \u0441 \u043f\u0440\u0438\u043c\u0435\u0440\u043e\u043c \u043f\u043e\u043a\u0430 \u043d\u0435 \u0437\u0430\u0433\u0440\u0443\u0436\u0435\u043d.")

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
        await message.answer("\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0440\u0430\u0441\u0441\u0447\u0438\u0442\u0430\u0439\u0442\u0435 \u043a\u0430\u0440\u0442\u0443.")

@dp.message_handler(lambda m: m.text == "🔮 Рассчитать" or "," in m.text)
async def calculate(message: types.Message):
    try:
        user_id = message.from_user.id
        parts = [x.strip() for x in message.text.split(",")]
        if len(parts) != 3:
            await message.answer("\u26a0\ufe0f \u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442. \u0412\u0432\u0435\u0434\u0438\u0442\u0435: \u0414\u0414.\u041c\u041c.\u0413\u0413\u0413\u0413, \u0427\u0427:\u041c\u041c, \u0413\u043e\u0440\u043e\u0434")
            return

        date_str, time_str, city = parts
        geo = requests.get(f"https://api.opencagedata.com/geocode/v1/json?q={city}&key={OPENCAGE_API_KEY}").json()
        if not geo.get("results"):
            await message.answer("\u274c \u0413\u043e\u0440\u043e\u0434 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")
            return

        lat = geo["results"][0]["geometry"]["lat"]
        lon = geo["results"][0]["geometry"]["lng"]
        lat_str = decimal_to_dms_str(lat, True)
        lon_str = decimal_to_dms_str(lon, False)

        tf = TimezoneFinder()
        timezone_str = tf.timezone_at(lat=lat, lng=lon)
        if timezone_str is None:
            await message.answer("\u274c \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u043f\u0440\u0435\u0434\u0435\u043b\u0438\u0442\u044c \u0447\u0430\u0441\u043e\u0432\u043e\u0439 \u043f\u043e\u044f\u0441. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u0433\u043e\u0440\u043e\u0434.")
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

        users[user_id] = {"pdf": pdf_path, "planets": {p: {"sign": chart.get(p).sign, "degree": chart.get(p).lon} for p in planets}, "paid": (user_id == admin_id)}

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

        await message.answer("🧠 Генерирую подробный отчёт... Это может занять 1–2 минуты.")

        planet_lines = "".join([f"{planet}: {info['sign']} ({round(info['degree'], 2)})\n" for planet, info in planets.items()])

        base_prompt = f"""
Ты — мудрый и опытный астропсихолог с 20-летним стажем. Составь ПОДРОБНЫЙ, человечный, глубокий и психологический астрологический отчёт. Избегай шаблонов, используй примеры, метафоры, обращайся к читателю лично.

Вот данные клиента по планетам:
{planet_lines}

1. Расскажи подробно о каждой планете: как она проявляется, влияет на личность, внутренние конфликты, дары и слабости.
2. Придумай логично дома для каждой планеты и опиши, как эти дома влияют на человека.
3. Придумай 3 значимых аспекта между планетами и раскрой их смысл.
4. Определи Асцендент и его влияние.
5. Дай рекомендации: по саморазвитию, отношениям, карьере.
6. Напиши красиво, вдумчиво, как консультацию.
        """

        res = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": base_prompt}],
            temperature=0.95,
            max_tokens=2800
        )
        full_text = res.choices[0].message.content.strip()

        # Генерация PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
        pdf.set_font("DejaVu", size=12)
        pdf.set_auto_page_break(auto=True, margin=15)

        for paragraph in full_text.split("\n\n"):
            for line in paragraph.split("\n"):
                pdf.multi_cell(0, 10, line)
            pdf.ln(4)

        paid_path = f"paid_{user_id}.pdf"
        pdf.output(paid_path)

        with open(paid_path, "rb") as f:
            await message.answer_document(f, caption="📄 Ваш подробный астрологический отчёт")

        report_usage[user_id] += 1

    except Exception as e:
        await message.answer(f"⚠️ Ошибка при генерации отчёта: {e}")

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
