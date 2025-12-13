import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from pathlib import Path

HISTORY_FILE = "history.json"

def load_persistent_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Streamlit не любит datetime в JSON → конвертируем обратно
            for entry in data["history"]:
                entry["ts"] = datetime.fromisoformat(entry["ts"])
            for entry in data["log"]:
                entry["ts"] = datetime.fromisoformat(entry["ts"])
            return data["history"], data["log"]
    return [], []

def save_persistent_history(history, log):
    # Конвертируем datetime → строка (JSON-совместимо)
    safe_history = [
        {k: (v.isoformat() if k == "ts" else v) for k, v in entry.items()}
        for entry in history
    ]
    safe_log = [
        {k: (v.isoformat() if k == "ts" else v) for k, v in entry.items()}
        for entry in log
    ]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"history": safe_history, "log": safe_log}, f, ensure_ascii=False, indent=2)

# ----------------------------
# Вспомогательные данные
# ----------------------------

@st.cache_data
def load_tech_table():
    return pd.read_csv("tech_table.csv")


tech_df = load_tech_table()

# Инициализация истории в сессии
if "history" not in st.session_state:
    st.session_state.history = []

if "log" not in st.session_state:
    st.session_state.log = []


# ----------------------------
# Функции диагностики
# ----------------------------

def get_norm_range(thickness, power):
    row = tech_df[(tech_df['thickness'] == thickness) & (tech_df['power'] == power)]
    if row.empty:
        return None, None
    return row['min_speed'].iloc[0], row['max_speed'].iloc[0]


def diagnose(thickness, power, speed):
    min_s, max_s = get_norm_range(thickness, power)
    if min_s is None:
        return "⚠️ Нет данных", "Нет данных в таблице", None, None

    if min_s <= speed <= max_s:
        return "Здоров", "Скорость реза в норме!", min_s, max_s
    elif speed < min_s * 0.9 or speed > max_s * 1.1:
        return "Неисправность", "Скорость вне допустимого диапазона!", min_s, max_s
    else:
        return "Проверка", "Скорость близка к границе нормы.", min_s, max_s


# ----------------------------
# UI
# ----------------------------

st.set_page_config(page_title="КИБЕР-ДОКТОР (MAX)", layout="wide")
st.title("🩺 КИБЕР-ДОКТОР — Полная версия")
st.caption("ИИ-диагностика с историей и прогнозом")

# ----------------------------
# Ввод текущих данных
# ----------------------------

with st.form("input_form"):
    col1, col2, col3 = st.columns(3)
    thickness = col1.number_input("Толщина, мм", min_value=1.0, max_value=10.0, value=3.0)
    power = col2.number_input("Мощность, кВт", min_value=1.0, max_value=10.0, value=3.0)
    speed = col3.number_input("Скорость, м/мин", min_value=0.1, value=3.2)
    submitted = st.form_submit_button("🔁 Зафиксировать показания")

# ----------------------------
# Сохранение данных и диагностика
# ----------------------------

if submitted:
    status, msg, min_s, max_s = diagnose(thickness, power, speed)
    timestamp = datetime.now()

    # Сохраняем в историю
    st.session_state.history.append({
        "ts": timestamp,
        "thickness": thickness,
        "power": power,
        "speed": speed,
        "status": status
    })

    # Лог событий
    st.session_state.log.append({
        "ts": timestamp,
        "event": f"Режим: {thickness}мм / {power}кВт → скорость {speed:.2f} м/мин → {status}"
    })

    # Анализ трендов (только если есть >=3 записей по тому же режиму)
    hist_df = pd.DataFrame(st.session_state.history)
    mode_mask = (hist_df['thickness'] == thickness) & (hist_df['power'] == power)
    mode_data = hist_df[mode_mask].sort_values('ts')

    if len(mode_data) >= 3:
        speeds = mode_data['speed'].values
        trend = np.polyfit(range(len(speeds)), speeds, 1)[0]  # наклон линии

        if trend < -0.1:  # снижение >0.1 м/мин за запись
            alert = "📉 Снижение эффективности: скорость падает при том же режиме."
            st.session_state.log.append({"ts": timestamp, "event": alert})
        if trend > 0.1 and speed > max_s * 0.9:
            alert = "📈 Подозрительно высокая скорость — возможна ошибка датчика."
            st.session_state.log.append({"ts": timestamp, "event": alert})

# ----------------------------
# Отображение текущего состояния
# ----------------------------

if st.session_state.history:
    last = st.session_state.history[-1]
    status, msg, min_s, max_s = diagnose(last["thickness"], last["power"], last["speed"])

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
# История и «Медицинская карта»
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
        st.caption(f"**{row['ts'].strftime('%H:%M:%S')}** — {row['event']}")

    # Прогнозная рекомендация (если есть >=2 аномалии)
    anomaly_keywords = ["снижение", "падает", "повышенное", "загрязн", "температура", "неисправность"]
    anomalies = [e for e in st.session_state.log if any(kw in e["event"].lower() for kw in anomaly_keywords)]
    if len(anomalies) >= 2:
        st.warning(
            "❗ **Прогнозная рекомендация:**\nНаблюдается несколько признаков деградации. Рекомендуется профилактическая проверка оптики и системы охлаждения.")

else:
    st.info("Нет данных. Нажмите «Зафиксировать показания», чтобы начать.")