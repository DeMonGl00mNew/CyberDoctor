# Импорты основных библиотек
import streamlit as st  # Фреймворк для веб-интерфейса
import pandas as pd  # Работа с табличными данными (технологическая таблица)
import numpy as np  # Математические вычисления (например, тренд скорости)
from datetime import datetime  # Работа с временными метками
import os  # Проверка существования файлов
import json  # Сохранение и загрузка истории в формате JSON
import plotly.graph_objects as go  # Интерактивная визуализация графиков
import requests  # HTTP-запросы к GigaChat API
from dotenv import load_dotenv  # Загрузка приватных ключей из .env

# Имена файлов, используемых приложением
HISTORY_FILE = "history.json"  # Файл для хранения истории операций и логов
TECH_TABLE_FILE = "tech_table.csv"  # Технологическая таблица: толщина, мощность → допустимая скорость
IMAGE_FILE = "laser_station.jpg"  # Схема лазерного станка для визуализации

# Загружаем переменные окружения (в т.ч. GIGACHAT_AUTH_KEY)
load_dotenv()


def get_gigachat_advice(status, msg, thickness, power, speed, min_s, max_s):
    """
    Запрашивает экспертный совет у GigaChat при статусах "Внимание" или "Неисправность".
    Возвращает строку с рекомендацией или сообщением об ошибке.
    """
    # Запрос ИИ-совета только при подозрительных статусах
    if status not in ("Внимание", "Неисправность"):
        return None

    # Получаем секретный ключ из переменных окружения
    auth_key = os.getenv("GIGACHAT_AUTH_KEY")
    if not auth_key:
        return "⚠️ Не задан GIGACHAT_AUTH_KEY."

    # === ШАГ 1: Получение access_token через OAuth 2.0 ===
    auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth  "  # URL для получения токена (лишние пробелы уберём в продакшене!)

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': 'fcad7112-80b3-456f-8ce3-31f533e5b5b2',  # Уникальный ID запроса (можно генерировать)
        'Authorization': f'Basic {auth_key}'  # Base64-encoded credentials (должны быть уже закодированы)
    }
    payload = {'scope': 'GIGACHAT_API_PERS'}  # Область доступа — персональная модель

    try:
        auth_response = requests.post(
            auth_url,
            data=payload,
            headers=headers,
            verify=False,  # Отключение проверки SSL (только для тестов!)
            timeout=10
        )

        # Обработка ошибок авторизации
        if auth_response.status_code != 200:
            error_detail = auth_response.text if auth_response.text else "No error details"
            return f"Ошибка {auth_response.status_code}: {error_detail}"

        result = auth_response.json()
        if 'access_token' not in result:
            return f"Токен не получен: {result}"

        access_token = result["access_token"]
    except Exception as e:
        return f"Сбой получения токена: {str(e)}"

    # === ШАГ 2: Запрос к чат-модели GigaChat ===
    system_prompt = (
        "Вы — инженер-эксперт по лазерной резке металлов. "
        "Дайте краткий (не более 2 предложений), практичный и технически точный совет. "
        "Не пишите вводные фразы — сразу суть."
    )
    user_prompt = (
        f"Статус станка: {status}. Диагностика: {msg}. "
        f"Параметры: толщина={thickness} мм, мощность={power} кВт, скорость={speed:.2f} м/мин. "
        f"Допустимый диапазон: {min_s}–{max_s} м/мин."
    )

    chat_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions  "  # URL API (лишние пробелы!)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "max_tokens": 100,  # Ограничение длины ответа
        "temperature": 0.3  # Низкая креативность — важна точность
    }

    try:
        response = requests.post(chat_url, json=payload, headers=headers, verify=False, timeout=15)
        if response.status_code == 200:
            data = response.json()
            advice = data["choices"][0]["message"]["content"].strip()
            return advice
        else:
            return f"GigaChat API ошибка {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return f"Сбой запроса: {str(e)}"


@st.cache_data
def load_tech_table():
    """
    Загружает технологическую таблицу из CSV-файла.
    Используется кэширование Streamlit, чтобы не читать файл при каждом взаимодействии.
    """
    if not os.path.exists(TECH_TABLE_FILE):
        st.error(f"Файл {TECH_TABLE_FILE} не найден!")
        st.stop()  # Останавливаем выполнение, если таблица отсутствует
    return pd.read_csv(TECH_TABLE_FILE)


def load_persistent_history():
    """
    Загружает историю операций и лог из JSON-файла.
    Преобразует строки времени в объекты datetime.
    Возвращает ([history], [log]) или ([], []) при ошибке/отсутствии файла.
    """
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Восстанавливаем datetime из ISO-строк для поля 'ts'
                history = [
                    {k: (datetime.fromisoformat(v) if k == "ts" else v) for k, v in entry.items()}
                    for entry in data.get("history", [])
                ]
                log = [
                    {k: (datetime.fromisoformat(v) if k == "ts" else v) for k, v in entry.items()}
                    for entry in data.get("log", [])
                ]
                return history, log
        except Exception as e:
            st.warning(f"Ошибка загрузки: {e}. Начинаем с чистого листа.")
    return [], []


def save_persistent_history(history, log):
    """
    Сохраняет историю и лог в JSON, преобразуя datetime в ISO-строки.
    """
    safe_history = [
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in entry.items()}
        for entry in history
    ]
    safe_log = [
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in entry.items()}
        for entry in log
    ]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"history": safe_history, "log": safe_log}, f, ensure_ascii=False, indent=2)


def get_norm_range(thickness, power, tech_df):
    """
    Находит допустимый диапазон скорости резки по толщине и мощности.
    Возвращает (min_speed, max_speed) или (None, None), если режим не найден.
    """
    row = tech_df[(tech_df['thickness'] == thickness) & (tech_df['power'] == power)]
    if row.empty:
        return None, None
    return row['min_speed'].iloc[0], row['max_speed'].iloc[0]


def diagnose(thickness, power, speed, tech_df):
    """
    Диагностика состояния станка:
    - "Здоров": скорость в пределах [min, max]
    - "Внимание": скорость в пределах [0.9*min, 1.1*max], но за пределами [min, max]
    - "Неисправность": скорость < 0.9*min или > 1.1*max
    Возвращает (статус, сообщение, min, max)
    """
    min_s, max_s = get_norm_range(thickness, power, tech_df)
    if min_s is None:
        return "⚠️ Нет данных", "Нет данных в таблице", None, None

    if min_s <= speed <= max_s:
        return "Здоров", "Скорость реза в норме!", min_s, max_s
    elif speed < min_s * 0.9 or speed > max_s * 1.1:
        return "Неисправность", "Скорость вне допустимого диапазона!", min_s, max_s
    else:
        return "Внимание", "Скорость близка к границе нормы.", min_s, max_s


# === ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ ===
# Загружаем технологическую таблицу один раз (благодаря @st.cache_data)
tech_df = load_tech_table()

# Загружаем историю и лог в сессию Streamlit, если они ещё не загружены
if "history" not in st.session_state or "log" not in st.session_state:
    hist, log = load_persistent_history()
    st.session_state.history = hist
    st.session_state.log = log

# Настраиваем внешний вид страницы
st.set_page_config(page_title="КИБЕР-ДОКТОР 🏥", layout="wide")

# === ВЕРХНЯЯ ПАНЕЛЬ: ЗАГОЛОВОК И ИНДИКАТОР СОСТОЯНИЯ ===
col_logo, col_status = st.columns([3, 1])
with col_logo:
    st.title("🩺 КИБЕР-ДОКТОР")
    st.caption("ИИ-мониторинг лазерного станка")
with col_status:
    if st.session_state.history:
        # Диагностика последней зафиксированной операции
        last = st.session_state.history[-1]
        status, _, _, _ = diagnose(last["thickness"], last["power"], last["speed"], tech_df)
        # Цветовая индикация состояния
        color_map = {"Здоров": "#4CAF50", "Внимание": "#FFC107", "Неисправность": "#F44336"}
        color = color_map.get(status, "#9E9E9E")
        st.markdown(
            f'<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: {color};">{status}</div>',
            unsafe_allow_html=True)
    else:
        st.markdown('<div style="text-align: center; color: gray;">Ожидание данных</div>', unsafe_allow_html=True)

# === ОСНОВНОЙ КОНТЕНТ: ВИЗУАЛИЗАЦИЯ И ВВОД ===
col_vis, col_input = st.columns([2, 1])

# Левая колонка: схема станка, прогресс, график
with col_vis:
    # Отображаем схему станка, если файл существует
    if os.path.exists(IMAGE_FILE):
        st.image(IMAGE_FILE, use_column_width=True)
    else:
        # Заглушка, если схема отсутствует
        st.markdown("""
        <div style="background: #f0f2f6; padding: 16px; border-radius: 8px; text-align: center; font-family: monospace;">
        [ СХЕМА ЛАЗЕРНОГО СТАНКА ]<br>
        🌡️ Источник │ ⚡ Мощность │ 🧭 Головка │ 💨 Охлаждение
        </div>
        """, unsafe_allow_html=True)

    # Пример текущей операции (можно заменить на реальные данные)
    st.write("**Текущая операция:** Резка детали #127")
    st.progress(68, text="Выполнено 68%")

    # График тренда скорости, если есть история
    if st.session_state.history and len(st.session_state.history) > 1:
        hist_df = pd.DataFrame(st.session_state.history)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_df['ts'],
            y=hist_df['speed'],
            mode='lines+markers',
            name='Скорость резки',
            line=dict(color='#2196F3')
        ))
        # Добавляем зону "Норма" на график (если возможно)
        last_row = hist_df.iloc[-1]
        min_s, max_s = get_norm_range(last_row['thickness'], last_row['power'], tech_df)
        if min_s is not None:
            fig.add_hrect(y0=min_s, y1=max_s, line_width=0, fillcolor="green", opacity=0.1,
                          annotation_text="Норма")
        fig.update_layout(height=200, margin=dict(l=0, r=0, t=30, b=0), title="Тренд скорости резки")
        st.plotly_chart(fig, use_container_width=True)

# Правая колонка: ввод параметров и диагноз
with col_input:
    # Форма для ввода оператором
    with st.form("input_form"):
        st.markdown("### 📥 Показания станка")
        thickness = st.number_input("📏 Толщина, мм", min_value=1.0, max_value=10.0, value=3.0)
        power = st.number_input("⚡ Мощность, кВт", min_value=1.0, max_value=10.0, value=3.0)
        speed = st.number_input("🧭 Скорость, м/мин", min_value=0.1, value=3.2)
        submitted = st.form_submit_button("🔁 Зафиксировать")

    st.divider()

    # Отображаем диагноз по последней операции
    if st.session_state.history:
        last = st.session_state.history[-1]
        status, msg, min_s, max_s = diagnose(last["thickness"], last["power"], last["speed"], tech_df)
        st.info(msg)

        # Визуализация: ползунок с текущей скоростью и зоной нормы
        if min_s is not None:
            st.slider(
                "**Скорость резки:**",
                float(min_s * 0.5), float(max_s * 1.5),
                float(last["speed"]),
                disabled=True,
                key="health_slider"
            )
            st.caption(f"Норма: {min_s}–{max_s} м/мин")

# === МЕДИКАРТА: ЖУРНАЛ СОБЫТИЙ ===
st.divider()
st.subheader("📋 Медикарта")
if st.session_state.log:
    log_df = pd.DataFrame(st.session_state.log)
    log_df["ts"] = pd.to_datetime(log_df["ts"])
    log_df = log_df.sort_values("ts", ascending=False)
    # Выводим события в обратном хронологическом порядке
    for _, row in log_df.iterrows():
        st.caption(f"**{row['ts'].strftime('%d.%m %H:%M')}** — {row['event']}")

    # Анализ аномалий: ищем ключевые слова, указывающие на проблемы
    anomaly_keywords = ["снижение", "падает", "повышенное", "загрязн", "температура", "неисправность", "ошибка"]
    anomalies = [e for e in st.session_state.log if any(kw in e["event"].lower() for kw in anomaly_keywords)]
    # Если найдено 2+ аномалии — даём прогнозную рекомендацию
    if len(anomalies) >= 2:
        st.warning(
            "❗ **Прогнозная рекомендация:**\nНаблюдается несколько признаков деградации. Рекомендуется профилактическая проверка оптики и системы охлаждения.")
else:
    st.info("Нет данных. Нажмите «Зафиксировать», чтобы начать.")

# === ОБРАБОТКА НОВОЙ ЗАПИСИ ===
if submitted:
    # Диагностика новых данных
    status, msg, min_s, max_s = diagnose(thickness, power, speed, tech_df)
    timestamp = datetime.now()

    # Сохраняем в историю операций
    st.session_state.history.append({
        "ts": timestamp,
        "thickness": thickness,
        "power": power,
        "speed": speed,
        "status": status
    })
    # Логируем событие
    st.session_state.log.append({
        "ts": timestamp,
        "event": f"Режим: {thickness}мм / {power}кВт → скорость {speed:.2f} м/мин → {status}"
    })

    # Анализ тренда для текущего режима (толщина + мощность)
    hist_df = pd.DataFrame(st.session_state.history)
    mode_mask = (hist_df['thickness'] == thickness) & (hist_df['power'] == power)
    mode_data = hist_df[mode_mask].sort_values('ts')
    if len(mode_data) >= 3:
        speeds = mode_data['speed'].values
        # Линейная регрессия: наклон > 0 — рост, < 0 — падение
        trend = np.polyfit(range(len(speeds)), speeds, 1)[0]
        if trend < -0.1:
            st.session_state.log.append({
                "ts": timestamp,
                "event": "📉 Снижение эффективности: скорость падает при том же режиме."
            })
        elif trend > 0.1 and speed > (max_s or 0) * 0.9:
            st.session_state.log.append({
                "ts": timestamp,
                "event": "📈 Подозрительно высокая скорость — возможна ошибка датчика."
            })

    # Запрос ИИ-совета при проблемах
    if status in ("Внимание", "Неисправность"):
        advice = get_gigachat_advice(status, msg, thickness, power, speed, min_s, max_s)
        if advice:
            st.session_state.log.append({
                "ts": timestamp,
                "event": f"🧠 GigaChat: {advice}"
            })

    # Сохраняем всё на диск
    save_persistent_history(st.session_state.history, st.session_state.log)
    # Перезагружаем страницу для отображения новых данных
    st.rerun()