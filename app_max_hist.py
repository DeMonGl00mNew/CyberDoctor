import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import os
import json

# ----------------------------
# Конфигурация
# ----------------------------
HISTORY_FILE = "history.json"
TECH_TABLE_FILE = "tech_table.csv"


# ----------------------------
# Вспомогательные функции
# ----------------------------

@st.cache_data
def load_tech_table():
    if not os.path.exists(TECH_TABLE_FILE):
        st.error(f"Файл {TECH_TABLE_FILE} не найден!")
        st.stop()
    return pd.read_csv(TECH_TABLE_FILE)


def load_persistent_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Восстанавливаем datetime
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
            st.warning(f"Ошибка загрузки истории: {e}. Начинаем с чистого листа.")
    return [], []


def save_persistent_history(history, log):
    # Преобразуем datetime → ISO-строка
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
    row = tech_df[(tech_df['thickness'] == thickness) & (tech_df['power'] == power)]
    if row.empty:
        return None, None
    return row['min_speed'].iloc[0], row['max_speed'].iloc[0]


def diagnose(thickness, power, speed, tech_df):
    min_s, max_s = get_norm_range(thickness, power, tech_df)
    if min_s is None:
        return "⚠️ Нет данных", "Нет данных в таблице", None, None

    if min_s <= speed <= max_s:
        return "Здоров", "Скорость реза в норме!", min_s, max_s
    elif speed < min_s * 0.9 or speed > max_s * 1.1:
        return "Неисправность", "Скорость вне допустимого диапазона!", min_s, max_s
    else:
        return "Проверка", "Скорость близка к границе нормы.", min_s, max_s


# ----------------------------
# Загрузка данных
# ----------------------------
tech_df = load_tech_table()
if "history" not in st.session_state or "log" not in st.session_state:
    hist, log = load_persistent_history()
    st.session_state.history = hist
    st.session_state.log = log

# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="КИБЕР-ДОКТОР (MAX + история)", layout="wide")
st.title("🩺 КИБЕР-ДОКТОР — Полная версия с памятью")
st.caption("История сохраняется между перезапусками")

# ----------------------------
# Ввод данных
# ----------------------------
with st.form("input_form"):
    col1, col2, col3 = st.columns(3)
    thickness = col1.number_input("Толщина, мм", min_value=1.0, max_value=10.0, value=3.0)
    power = col2.number_input("Мощность, кВт", min_value=1.0, max_value=10.0, value=3.0)
    speed = col3.number_input("Скорость, м/мин", min_value=0.1, value=3.2)
    submitted = st.form_submit_button("🔁 Зафиксировать показания")

# ----------------------------
# Обработка новых данных
# ----------------------------
if submitted:
    status, msg, min_s, max_s = diagnose(thickness, power, speed, tech_df)
    timestamp = datetime.now()

    # Добавляем в историю
    st.session_state.history.append({
        "ts": timestamp,
        "thickness": thickness,
        "power": power,
        "speed": speed,
        "status": status
    })
    st.session_state.log.append({
        "ts": timestamp,
        "event": f"Режим: {thickness}мм / {power}кВт → скорость {speed:.2f} м/мин → {status}"
    })

    # Анализ тренда
    hist_df = pd.DataFrame(st.session_state.history)
    mode_mask = (hist_df['thickness'] == thickness) & (hist_df['power'] == power)
    mode_data = hist_df[mode_mask].sort_values('ts')

    if len(mode_data) >= 3:
        speeds = mode_data['speed'].values
        trend = np.polyfit(range(len(speeds)), speeds, 1)[0]
        if trend < -0.1:
            alert = "📉 Снижение эффективности: скорость падает при том же режиме."
            st.session_state.log.append({"ts": timestamp, "event": alert})
        elif trend > 0.1 and speed > (max_s or 0) * 0.9:
            alert = "📈 Подозрительно высокая скорость — возможна ошибка датчика."
            st.session_state.log.append({"ts": timestamp, "event": alert})

    # Сохраняем на диск
    save_persistent_history(st.session_state.history, st.session_state.log)
    st.success("Данные сохранены!")

# ----------------------------
# Текущее состояние
# ----------------------------
if st.session_state.history:
    last = st.session_state.history[-1]
    status, msg, min_s, max_s = diagnose(last["thickness"], last["power"], last["speed"], tech_df)
    color_map = {"Здоров": "#4CAF50", "Проверка": "#FFC107", "Неисправность": "#F44336"}
    color = color_map.get(status, "#9E9E9E")
    st.markdown(f"<h2 style='color:{color}; text-align:center;'>{status}</h2>", unsafe_allow_html=True)
    st.info(msg)

    if min_s is not None:
        st.slider(
            "**Скорость резки (м/мин):**",
            float(min_s * 0.5), float(max_s * 1.5),
            float(last["speed"]),
            disabled=True
        )
        st.caption(f"Норма: {min_s}–{max_s} м/мин")

# ----------------------------
# История и журнал
# ----------------------------
st.divider()
st.subheader("📊 История режимов")
if st.session_state.history:
    hist_df = pd.DataFrame(st.session_state.history)
    hist_df["ts"] = pd.to_datetime(hist_df["ts"])
    st.dataframe(hist_df[["ts", "thickness", "power", "speed", "status"]].sort_values("ts", ascending=False),
                 use_container_width=True)

st.subheader("📋 Медицинская карта (журнал событий)")
if st.session_state.log:
    log_df = pd.DataFrame(st.session_state.log)
    log_df["ts"] = pd.to_datetime(log_df["ts"])
    log_df = log_df.sort_values("ts", ascending=False)
    for _, row in log_df.iterrows():
        st.caption(f"**{row['ts'].strftime('%d.%m %H:%M')}** — {row['event']}")

    # Прогноз при >=2 тревогах
    anomaly_keywords = ["снижение", "падает", "повышенное", "загрязн", "температура", "неисправность", "ошибка"]
    anomalies = [e for e in st.session_state.log if any(kw in e["event"].lower() for kw in anomaly_keywords)]
    if len(anomalies) >= 2:
        st.warning(
            "❗ **Прогнозная рекомендация:**\nНаблюдается несколько признаков деградации. Рекомендуется профилактическая проверка оптики и системы охлаждения.")
else:
    st.info("Нет данных. Нажмите «Зафиксировать показания», чтобы начать.")