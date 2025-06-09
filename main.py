# ... (все импорты и переменные как у тебя — без изменений)

# Хендлер: start
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "👋 Добро пожаловать в *Моя Натальная Карта*! Узнай свою судьбу по дате рождения ✨",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# Хендлер: Начать расчёт
@dp.message_handler(lambda m: m.text == "🚀 Начать расчёт")
async def begin(message: types.Message):
    await message.answer("Введите данные: ДД.ММ.ГГГГ, ЧЧ:ММ, Город", reply_markup=main_kb)

# Хендлер: Пример отчёта
@dp.message_handler(lambda m: m.text == "📊 Пример платного отчёта")
async def example_pdf(message: types.Message):
    try:
        with open("example_paid_astrology_report.pdf", "rb") as f:
            await message.answer_document(f)
    except:
        await message.answer("Файл с примером пока не загружен.")

# Хендлер: Скачать PDF
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

# Хендлер: Рассчитать
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

        planet_names = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
        summary = []
        for p in planet_names:
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
            "planets": {
                p: {
                    "sign": chart.get(p).sign,
                    "degree": chart.get(p).lon,
                    "house": chart.get(p).house
                } for p in planet_names
            },
            "lat": lat,
            "lon": lon,
            "city": city,
            "date_str": date_str,
            "time_str": time_str,
            "dt_utc": dt
        }

        await message.answer("✅ Готово. Хочешь подробный отчёт? Нажми 📄 Заказать подробный отчёт")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# Хендлер: Подробный отчёт
@dp.message_handler(lambda m: m.text == "📄 Заказать подробный отчёт")
async def send_detailed_parts(message: types.Message):
    user_id = message.from_user.id
    user_data = users.get(user_id)
    if not user_data:
        await message.answer("❗ Сначала сделайте расчёт.")
        return

    first_name = message.from_user.first_name or "Дорогой друг"
    date_str = user_data.get("date_str", "Неизвестно")
    time_str = user_data.get("time_str", "Неизвестно")
    city = user_data.get("city", "Неизвестно")
    dt_utc = user_data.get("dt_utc")
    lat = user_data.get("lat")
    lon = user_data.get("lon")
    dt_utc_str = dt_utc.strftime("%Y-%m-%d %H:%M") if dt_utc else "Неизвестно"

    planet_lines = "\n".join([
        f"{planet}: {info['sign']} ({round(info['degree'], 2)}°), Дом: {info.get('house', '?')}"
        for planet, info in user_data.get("planets", {}).items()
    ])

    header = f"""
Имя: {first_name}
Дата: {date_str}
Время: {time_str}
Город: {city}
UTC: {dt_utc_str}
Широта: {lat}
Долгота: {lon}
Планеты:
{planet_lines}
"""

    sections = [
        ("Планеты", "Опиши подробно каждую из планет и её влияние на характер, личность, конфликты, дары."),
        ("Дома", "Определи дома и объясни их влияние, как дома взаимодействуют с планетами."),
        ("Аспекты", "Придумай и опиши 3 ключевых аспекта между планетами и их влияние."),
        ("Асцендент", "Определи Асцендент и опиши, как он влияет на внешность и поведение."),
        ("Рекомендации", "Дай советы по саморазвитию, карьере, любви. Напиши человечно."),
    ]

    for title, instruction in sections:
        prompt = f"""
Ты опытный астролог-психолог. Используй данные ниже для анализа.

{header}

Задача: {instruction}
        """
        try:
            res = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=2000
            )
            content = res.choices[0].message.content.strip()

            pdf = FPDF()
            pdf.add_page()
            pdf.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            pdf.set_font("DejaVu", size=12)
            pdf.set_auto_page_break(auto=True, margin=15)

            for paragraph in content.split("\n\n"):
                for line in paragraph.split("\n"):
                    pdf.multi_cell(0, 10, line)
                pdf.ln(3)

            filename = f"{user_id}_{title}.pdf"
            pdf.output(filename)
            with open(filename, "rb") as f:
                await message.answer_document(f, caption=f"📘 Отчёт: {title}")

        except Exception as e:
            await message.answer(f"⚠️ Ошибка при генерации {title}: {e}")

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
