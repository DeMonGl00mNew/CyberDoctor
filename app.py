import streamlit as st
import pandas as pd

# Загрузка таблицы
@st.cache_data
def load_tech_table():
    return pd.read_csv("tech_table.csv")

tech_df = load_tech_table()

st.title("🩺 КИБЕР-ДОКТОР")
st.subheader("Диагностика лазерного станка")

# Ввод параметров
col1, col2, col3 = st.columns(3)
thickness = col1.number_input("Толщина материала, мм", min_value=1.0, max_value=10.0, value=3.0)
power = col2.number_input("Мощность лазера, кВт", min_value=1.0, max_value=10.0, value=3.0)
actual_speed = col3.number_input("Фактическая скорость, м/мин", min_value=0.1, value=3.2)

# Поиск нормы
row = tech_df[(tech_df['thickness'] == thickness) & (tech_df['power'] == power)]

if row.empty:
    st.warning("⚠️ Нет данных в технологической таблице для этой комбинации.")
else:
    min_speed = row['min_speed'].iloc[0]
    max_speed = row['max_speed'].iloc[0]

    # Диагноз
    if min_speed <= actual_speed <= max_speed:
        status = "🟢 Здоров"
        message = "Скорость резки в норме!"
        color = "#4CAF50"
    elif actual_speed < min_speed * 0.9 or actual_speed > max_speed * 1.1:
        status = "🔴 Неисправность"
        message = "Скорость резки вне допустимого диапазона!"
        color = "#F44336"
    else:
        status = "🟡 Требуется проверка"
        message = "Скорость резки близка к границе нормы. Проверьте настройки."
        color = "#FFC107"

    # Визуализация
    st.markdown(f"<h2 style='color:{color}; text-align:center;'>{status}</h2>", unsafe_allow_html=True)
    st.info(message)

    # Шкала здоровья
    st.write("**Скорость резки:**")
    st.slider(
        "",
        min_speed * 0.5,
        max_speed * 1.5,
        actual_speed,
        disabled=True,
        format="%.2f м/мин"
    )
    st.caption(f"Норма: {min_speed}–{max_speed} м/мин")