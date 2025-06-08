from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import logging, os, openai
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib.chart import Chart
from fpdf import FPDF
from pathlib import Path

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

admin_user_id = 7943520249

kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add(KeyboardButton("🚀 Начать расчёт"))

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("🔮 Рассчитать", "📄 Скачать PDF")
main_kb.add("💰 Заказать подробный отчёт", "📊 Пример платного отчёта")


def generate_paid_pdf_report(user_id):
    content = [
        "🌞 Солнце в Весах — стремление к гармонии, дипломатичность, любовь к красоте и балансу.",
        "🌝 Луна в Раке — повышенная чувствительность, потребность в заботе, эмоциональная стабильность.",
        "☿ Меркурий в Весах — логичное и взвешенное мышление, стремление к справедливости в речи.",
        "♀ Венера в Деве — аналитический подход к любви, перфекционизм в отношениях.",
        "♂ Марс в Деве — трудолюбие, точность в действиях, внутренняя дисциплина.",
        "♃ Юпитер в Водолее — любовь к свободе, философия гуманизма, широкий круг интересов.",
        "♄ Сатурн в Стрельце — устойчивые убеждения, ответственность в обучении.",
        "⚷ Хирон в Тельце — душевная рана, связанная с материальной стабильностью.",
        "⚡ Аспекты: Марс квадрат Сатурн — внутренние конфликты между действием и ответственностью.",
        "❤️ Любовные аспекты: Венера секстиль Луна — эмоциональное согласие в любви.",
        "🎯 Кармическая задача: развить чувство собственного достоинства и умение идти на компромиссы.",
        "💼 Профессии: дипломат, дизайнер, психотерапевт, исследователь.",
        "💰 Финансовый потенциал: благоприятен в сфере консультирования и искусства."
    ]

    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
    pdf.set_font("DejaVu", size=12)

    for line in content:
        pdf.multi_cell(0, 10, line)

    filename = f"{user_id}_full.pdf"
    pdf.output(filename)
    return filename


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
    example_path = "example_paid_astrology_report.pdf"
    if Path(example_path).exists():
        with open(example_path, "rb") as f:
            await message.answer_document(f)
    else:
        await message.answer("Файл с примером пока не загружен.")

@dp.message_handler()
async def handle_input(message: types.Message):
    await message.answer("🔄 Выполняется расчёт...")

    if message.from_user.id == admin_user_id:
        pdf_path = generate_paid_pdf_report(message.from_user.id)
        if Path(pdf_path).exists():
            with open(pdf_path, "rb") as f:
                await message.answer_document(f, caption="📩 Вот ваш подробный астрологический отчёт.")
        else:
            await message.answer("⚠️ Ошибка генерации PDF.")
    else:
        await message.answer("🆓 Вы получили бесплатную часть! Для полного отчёта нажмите \"💰 Заказать подробный отчёт\".")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
