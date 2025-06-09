import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Дашборд по звонкам",
    layout="wide",
    initial_sidebar_state="expanded"
)


def apply_global_styles():
    """Применяет глобальные стили CSS для дашборда"""
    st.markdown("""
    <style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 5px solid #1976D2;
        margin-bottom: 1rem;
    }
    .metric-title {
        font-size: 14px;
        font-weight: bold;
        color: #333;
        margin-bottom: 0.5rem;
    }
    .metric-value {
        font-size: 28px;
        font-weight: bold;
        color: #1976D2;
    }
    .section-header {
        font-size: 20px;
        font-weight: bold;
        color: #1976D2;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 2px solid #1976D2;
        padding-bottom: 0.5rem;
    }
    </style>
    """, unsafe_allow_html=True)


def create_metric_card(title, value, delta=None):
    """Создает HTML-карточку для отображения метрики"""
    delta_html = f"<div style='color: green; font-size: 14px;'>▲ {delta}</div>" if delta else ""
    return f"""
    <div class="metric-card">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        {delta_html}
    </div>
    """


def get_prev_sheet(sheet_name):
    """Автоматически определяет название листа предыдущего месяца"""
    months = [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
        "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ]
    for i, month in enumerate(months):
        if month in sheet_name:
            prev_month = months[i - 1] if i > 0 else months[-1]
            return sheet_name.replace(month, prev_month)
    return None


def normalize_date(col):
    """Нормализует формат даты в колонке"""
    try:
        if isinstance(col, pd.Timestamp):
            return col.strftime('%Y-%m-%d')
        if isinstance(col, str):
            try:
                dt = pd.to_datetime(col, errors='coerce')
                if pd.notna(dt):
                    return dt.strftime('%Y-%m-%d')
            except:
                pass
        return str(col)
    except Exception as e:
        logger.warning(f"Ошибка нормализации даты {col}: {e}")
        return str(col)


def find_metric_value(df_agg, metric_name_part):
    """
    Безопасно ищет значение метрики в агрегированном DataFrame по частичному совпадению названия.
    Возвращает значение или 0, если метрика не найдена.
    """
    if df_agg.empty or 'Показатель' not in df_agg.columns or 'Сумма за период' not in df_agg.columns:
        return 0

    try:
        match = df_agg[df_agg['Показатель'].str.contains(metric_name_part, na=False, case=False)]
        if not match.empty:
            value = match['Сумма за период'].iloc[0]
            return pd.to_numeric(value, errors='coerce') or 0
    except Exception as e:
        logger.warning(f"Ошибка поиска метрики '{metric_name_part}': {e}")

    return 0
# НОВАЯ ФУНКЦИЯ: Для безопасного извлечения среднего значения по дням
def find_metric_average_daily(df_containing_daily_data, metric_name_part, columns_to_average):
    """
    Ищет строку метрики в DataFrame с ежедневными данными и вычисляет среднее значение
    для указанного диапазона дней, игнорируя пустые/нечисловые ячейки.
    Возвращает среднее значение (как долю, например 0.xx) или 0, если метрика не найдена
    или нет числовых данных для усреднения.
    Также обрабатывает значения в виде '85%' или '85'.
    """
    if not df_containing_daily_data.empty and columns_to_average:
        match = df_containing_daily_data[
            df_containing_daily_data['Показатель'].str.contains(metric_name_part, na=False, case=False)]
        if not match.empty:
            daily_values = match[columns_to_average].iloc[0]

            # Обработка значений типа '85%' или '85'
            daily_values_cleaned = daily_values.astype(str).str.replace('%', '', regex=False)

            # ИЗМЕНЕНИЕ ЗДЕСЬ: Убираем .fillna(0)
            numeric_daily_values = pd.to_numeric(daily_values_cleaned, errors='coerce')  # Теперь NaN остаются

            # Отфильтровываем NaN перед усреднением, чтобы они не влияли
            numeric_daily_values = numeric_daily_values.dropna()

            # Если после отфильтровывания NaN не осталось числовых данных, возвращаем 0
            if numeric_daily_values.empty:
                return 0

            # Эвристика: если среднее сильно больше 1, считаем, что это были целые проценты
            if numeric_daily_values.mean() > 1 and numeric_daily_values.max() > 100:
                return numeric_daily_values.mean() / 100.0
            else:
                return numeric_daily_values.mean()
    return 0


def get_daily_values(df_period, metric_name_part, selected_cols_list):
    """Извлекает ежедневные значения для построения графиков динамики"""
    if df_period.empty or not selected_cols_list:
        return [0] * len(selected_cols_list)

    try:
        match = df_period[df_period['Показатель'].str.contains(metric_name_part, na=False, case=False)]
        if not match.empty:
            values = match[selected_cols_list].iloc[0]
            return pd.to_numeric(values, errors='coerce').fillna(0).tolist()
    except Exception as e:
        logger.warning(f"Ошибка получения ежедневных значений для '{metric_name_part}': {e}")

    return [0] * len(selected_cols_list)


def process_data(df, selected_cols):
    """Обрабатывает данные и возвращает агрегированный DataFrame"""
    if df.empty or not selected_cols:
        return pd.DataFrame(), pd.DataFrame()

    try:
        # Создаем копию с нужными колонками
        data_period = df[['Показатель'] + selected_cols].copy()

        # Преобразуем числовые колонки
        num_data = data_period[selected_cols].apply(pd.to_numeric, errors='coerce').fillna(0)

        # Создаем агрегированные данные
        data_period_aggregated = data_period[['Показатель']].copy()
        data_period_aggregated['Сумма за период'] = num_data.sum(axis=1)

        return data_period, data_period_aggregated
    except Exception as e:
        logger.error(f"Ошибка обработки данных: {e}")
        return pd.DataFrame(), pd.DataFrame()


def create_dynamics_chart(data_period, selected_cols, start_day, end_day):
    """Создает график динамики звонков"""
    try:
        days_for_chart = list(range(start_day, end_day + 1))

        # Получаем ежедневные данные
        incoming_values = get_daily_values(data_period, "Входящие звонки - ВЗ", selected_cols)
        accepted_values = get_daily_values(data_period, "Принятые ВЗ", selected_cols)
        missed_values = get_daily_values(data_period, "Непринятые ВЗ", selected_cols)
        forwarded_values = get_daily_values(data_period, "Переадресованные успешно ВЗ", selected_cols)

        chart_df = pd.DataFrame({
            "День": days_for_chart,
            "Входящие": incoming_values,
            "Принятые": accepted_values,
            "Непринятые": missed_values,
            "Переадресованные успешно": forwarded_values,
        })

        chart_long = chart_df.melt(
            id_vars="День",
            value_vars=["Входящие", "Принятые", "Непринятые", "Переадресованные успешно"],
            var_name="Категория",
            value_name="Количество"
        )

        fig_line = px.line(
            chart_long,
            x="День", y="Количество", color="Категория",
            labels={'Количество': 'Звонки', 'День': 'День месяца'},
            title=f"Динамика входящих звонков по дням (Дни {start_day}-{end_day})",
            range_y=[0, max(chart_df[["Входящие", "Принятые", "Непринятые", "Переадресованные успешно"]].max()) + 5]
        )

        fig_line.update_xaxes(dtick=1, tickfont=dict(size=14))
        fig_line.update_yaxes(tickfont=dict(size=14))
        fig_line.update_layout(
            title_font_size=18,
            legend=dict(font=dict(size=14)),
            font=dict(size=12)
        )

        return fig_line
    except Exception as e:
        logger.error(f"Ошибка создания графика динамики: {e}")
        return None


def create_funnel_chart(data_period_aggregated, start_day, end_day):
    """Создает воронку обработки звонков"""
    try:
        total_incoming_agg = find_metric_value(data_period_aggregated, "Входящие звонки - ВЗ")
        accepted_vz_agg = find_metric_value(data_period_aggregated, "Принятые ВЗ")
        forwarded_success_vz_agg = find_metric_value(data_period_aggregated, "Переадресованные успешно ВЗ")
        missed_vz_agg = find_metric_value(data_period_aggregated, "Непринятые ВЗ")

        funnel_labels = [
            "Всего входящих",
            "Принятые ВЗ",
            "Переадресованные успешно ВЗ",
            "Непринятые ВЗ"
        ]
        funnel_values = [total_incoming_agg, accepted_vz_agg, forwarded_success_vz_agg, missed_vz_agg]
        funnel_colors = ["#1976D2", "green", "yellow", "red"]

        fig_funnel = go.Figure(go.Funnel(
            y=funnel_labels,
            x=funnel_values,
            textinfo="value",
            textfont=dict(size=14),
            marker={"color": funnel_colors, "line": {"width": 0}},
            connector={"line": {"color": "white", "width": 1}}
        ))
        fig_funnel.update_layout(
            title=f"Воронка обработки звонков (Дни {start_day}-{end_day})",
            title_font_size=18,
            width=600, height=500,
            margin=dict(l=40, r=40, t=60, b=40),
            font=dict(size=14)
        )

        return fig_funnel
    except Exception as e:
        logger.error(f"Ошибка создания воронки обработки: {e}")
        return None


def create_staff_charts(data_period_aggregated, start_day, end_day):
    """Создает графики статистики сотрудников"""
    try:
        staff_indicator_names = [
            "Зарема", "Мади", "Алишер",
        ]
        staff_data = data_period_aggregated[data_period_aggregated['Показатель'].isin(staff_indicator_names)].copy()

        if staff_data.empty:
            return None, None

        staff_names = staff_data['Показатель'].values
        staff_forwarded = staff_data['Сумма за период'].values

        bar_df = pd.DataFrame({
            "Сотрудник": staff_names,
            "Переадресовано успешно ВЗ": staff_forwarded
        })

        fig_staff = px.bar(
            bar_df,
            x="Сотрудник",
            y="Переадресовано успешно ВЗ",
            title=f"Переадресовано успешно ВЗ по сотрудникам (Дни {start_day}-{end_day})",
            text_auto=True
        )
        fig_staff.update_layout(
            width=600,
            title_font_size=18,
            font=dict(size=12)
        )
        fig_staff.update_xaxes(tickfont=dict(size=12))
        fig_staff.update_yaxes(tickfont=dict(size=12))
        fig_staff.update_traces(textfont_size=12)

        # Круговая диаграмма для троих сотрудников
        target_staff = ["Зарема", "Мади", "Алишер"]
        pie_df = bar_df[bar_df["Сотрудник"].isin(target_staff)]

        fig_pie = None
        if not pie_df.empty:
            fig_pie = px.pie(
                pie_df,
                names="Сотрудник",
                values="Переадресовано успешно ВЗ",
                title=f"Переадресовано успешно ВЗ (Зарема, Мади, Алишер) (Дни {start_day}-{end_day})"
            )
            fig_pie.update_traces(
                textinfo='percent+value+label',
                textfont_size=14
            )
            fig_pie.update_layout(
                title_font_size=18,
                legend=dict(font=dict(size=14)),
                font=dict(size=12)
            )

        return fig_staff, fig_pie
    except Exception as e:
        logger.error(f"Ошибка создания графиков сотрудников: {e}")
        return None, None


def create_internet_chart(data_period_aggregated, start_day, end_day):
    """Создает график интернет-заявок"""
    try:
        iz_labels = ["Дозвонились ИЗ", "Не обработаны ИЗ", "Не дозвонились ИЗ"]
        iz_values = []
        for label in iz_labels:
            value = find_metric_value(data_period_aggregated, label)
            iz_values.append(value)

        if all(v == 0 for v in iz_values):
            return None

        iz_df = pd.DataFrame({
            "Статус": iz_labels,
            "Количество": iz_values
        })

        fig_iz = px.pie(
            iz_df,
            names="Статус",
            values="Количество",
            title=f"Распределение интернет-заявок (ИЗ) (Дни {start_day}-{end_day})",
            color="Статус",
            color_discrete_map={
                "Дозвонились ИЗ": "green",
                "Не обработаны ИЗ": "red",
                "Не дозвонились ИЗ": "yellow"
            }
        )
        fig_iz.update_traces(
            textinfo='none',
            textposition='outside',
            texttemplate='%{label}: %{value} (%{percent})',
            textfont_size=12
        )
        fig_iz.update_layout(
            legend_title_text='Статус',
            title_font_size=16,
            legend=dict(font=dict(size=12)),
            font=dict(size=12)
        )

        return fig_iz
    except Exception as e:
        logger.error(f"Ошибка создания графика интернет-заявок: {e}")
        return None


# Теперь она принимает data_period и selected_cols вместо data_period_aggregated
def create_scripts_chart(data_period, selected_cols, start_day, end_day): # <<< Изменены параметры
    """Создает график выполнения скриптов"""
    try:
        script_labels_parts = ["Выполнение скрипта Зарема", "Выполнение скрипта Мади",
                               "Выполнение скрипта Алишер"]
        script_names = ["Зарема", "Мади", "Алишер"]
        script_percents = []
        for label_part in script_labels_parts:
            # Используем find_metric_average_daily и передаем ей data_period и selected_cols
            value = find_metric_average_daily(data_period, label_part, selected_cols) # <<< ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ И ПАРАМЕТРЫ
            script_percents.append(value * 100) # Умножаем на 100, потому что find_metric_average_daily вернет 0.xx

        # Цвета по правилам (если они в функции)
        script_colors = [
            "red" if v < 50 else "orange" if v < 80 else "green"
            for v in script_percents
        ]

        script_df = pd.DataFrame({
            "Менеджер": script_names,
            "Выполнение скрипта (%)": pd.Series(script_percents).round(1),
            "Цвет": script_colors
        })

        fig_script = px.bar(
            script_df,
            x="Менеджер",
            y="Выполнение скрипта (%)",
            color="Цвет",
            color_discrete_map={
                "red": "red",
                "orange": "orange",
                "green": "green"
            },
            text="Выполнение скрипта (%)",
            title=f"Выполнение скрипта по менеджерам (Дни {start_day}-{end_day})"
        )
        fig_script.update_traces(textposition='outside', textfont_size=12)
        fig_script.update_layout(
            showlegend=False,
            yaxis=dict(range=[0, 100], tickfont=dict(size=12)),
            xaxis=dict(tickfont=dict(size=12)),
            title_font_size=18,
            font=dict(size=12)
        )
        return fig_script
    except Exception as e:
        # st.error(f"Ошибка при создании графика выполнения скриптов: {e}") # Можете добавить для отладки
        logger.error(f"Ошибка при создании графика скриптов: {e}")
        return None


def create_sales_funnel_chart(data_period_aggregated, start_day, end_day):
    """Создает воронку продаж с суммированием показателей"""
    try:
        # Суммируем показатели для "Общие звонки"
        call_indicators = [
            "Зарема",
            "Мади",
            "Алишер",
            "Думан",
            "ИНТЕРНЕТ ЗАЯВКИ - ИЗ"
        ]

        total_calls = sum([
            find_metric_value(data_period_aggregated, indicator)
            for indicator in call_indicators
        ])
        visits = find_metric_value(data_period_aggregated, "Визиты")
        test_drives = find_metric_value(data_period_aggregated, "Тест-драйвы")
        commercial_offers = find_metric_value(data_period_aggregated, "КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ")

        # Автоматическое суммирование всех показателей содержащих "Контракт"
        contracts = 0
        contract_rows = data_period_aggregated[
            data_period_aggregated['Показатель'].str.contains('Контракт', na=False, case=False)
        ]
        if not contract_rows.empty:
            contracts = contract_rows['Сумма за период'].sum()

        # Автоматическое суммирование всех показателей содержащих "Выдач"
        deliveries = 0
        delivery_rows = data_period_aggregated[
            data_period_aggregated['Показатель'].str.contains('Выдач', na=False, case=False)
        ]
        if not delivery_rows.empty:
            deliveries = delivery_rows['Сумма за период'].sum()

        funnel2_labels = [
            "Общие звонки", "Визиты", "Тест-драйвы", "Коммерческие предложения", "Контракты", "Выдачи"
        ]
        funnel2_values = [total_calls, visits, test_drives, commercial_offers, contracts, deliveries]

        if all(v == 0 for v in funnel2_values):
            return None

        fig_funnel2 = go.Figure(go.Funnel(
            y=funnel2_labels,
            x=funnel2_values,
            textinfo="value+percent previous",
            connector={"line": {"color": "gray", "width": 2}}
        ))
        fig_funnel2.update_layout(
            title=f"Воронка продаж (Дни {start_day}-{end_day})",
            width=500, height=400,
            margin=dict(l=40, r=40, t=60, b=40)
        )

        return fig_funnel2
    except Exception as e:
        logger.error(f"Ошибка создания воронки продаж: {e}")
        return None


def create_reasons_chart(df, data_period_aggregated, start_day, end_day):
    """Создает график причин отказов"""
    try:
        reasons_labels = []
        reasons_values = []

        # Ищем начало секции "ОТКАЗЫ" в DataFrame
        start_index = None
        for i in range(df.shape[0]):
            if pd.notna(df.iloc[i, 0]) and "ОТКАЗЫ" in str(df.iloc[i, 0]).upper():
                start_index = i + 1  # Начинаем с следующей строки после заголовка
                break

        # Если не нашли секцию ОТКАЗЫ, начинаем с 37-й строки (как в оригинале)
        if start_index is None:
            start_index = 37

        # Ищем причины отказа
        for i in range(start_index, df.shape[0]):
            if i >= df.shape[0]:
                break

            indicator_name = df.iloc[i, 0]

            # Пропускаем пустые строки
            if pd.isna(indicator_name) or str(indicator_name).strip() == "":
                continue

            # Останавливаемся, если дошли до следующей секции (например, начинающейся с заглавных букв)
            indicator_str = str(indicator_name).strip()
            if (indicator_str.isupper() and len(indicator_str) > 3 and
                    not any(keyword in indicator_str.lower() for keyword in
                            ['заявку', 'купил', 'авто', 'не', 'отказ', 'ошибочно', 'телефон', 'без'])):
                break

            # Пытаемся найти этот показатель в агрегированных данных
            value = find_metric_value(data_period_aggregated, indicator_str)
            if value > 0:
                reasons_labels.append(indicator_str)
                reasons_values.append(value)

        if not reasons_labels:
            return None

        reasons_df = pd.DataFrame({
            "Причина отказа": reasons_labels,
            "Количество": reasons_values
        }).sort_values("Количество", ascending=True)

        # Ограничиваем количество отображаемых причин для лучшей читаемости
        if len(reasons_df) > 10:
            reasons_df = reasons_df.tail(10)

        textpositions = ['outside' if v < reasons_df["Количество"].max() * 0.3 else 'auto' for v in
                         reasons_df["Количество"]]

        fig_reasons = go.Figure(go.Bar(
            y=reasons_df["Причина отказа"],
            x=reasons_df["Количество"],
            orientation='h',
            text=reasons_df["Количество"],
            textposition=textpositions,
            marker_color='#1976D2'
        ))

        fig_reasons.update_layout(
            title=f"Причины отказа (Дни {start_day}-{end_day})",
            height=max(400, len(reasons_df) * 40),  # Динамическая высота в зависимости от количества причин
            margin=dict(l=250, r=40, t=60, b=40)  # Увеличили левый отступ для длинных названий
        )

        return fig_reasons
    except Exception as e:
        logger.error(f"Ошибка создания графика причин отказов: {e}")
        return None


def main():
    """Основная функция приложения"""
    apply_global_styles()

    st.title("Дашборд по звонкам")
    st.write("Загрузите актуальный Excel-файл с данными")

    # Загрузка файла
    uploaded_file = st.file_uploader("Выберите Excel-файл", type=["xlsx"])

    if uploaded_file is None:
        st.warning("Пожалуйста, загрузите файл для начала работы.")
        return

    try:
        # Чтение Excel файла
        xl = pd.ExcelFile(uploaded_file)
        sheet_names = [s for s in xl.sheet_names if s.startswith("Отчет")]

        if not sheet_names:
            st.error("В файле не найдено листов, начинающихся с 'Отчет'")
            return

        selected_sheet = st.selectbox("Выберите лист (текущий месяц)", sheet_names)

        # Определение предыдущего листа
        prev_sheet = get_prev_sheet(selected_sheet)

        # Загрузка данных
        df = xl.parse(selected_sheet)
        df_prev = xl.parse(prev_sheet) if prev_sheet and prev_sheet in sheet_names else None

        # Настройки сайдбара
        st.sidebar.header("⚙️ Настройки отображения")
        show_data_preview = st.sidebar.checkbox("Показать предпросмотр данных", value=False)
        show_metrics = st.sidebar.checkbox("Показать ключевые метрики", value=True)

        st.sidebar.header("📊 Разделы дашборда")
        show_dynamics = st.sidebar.checkbox("Динамика звонков", value=True)
        show_funnel = st.sidebar.checkbox("Воронка обработки", value=True)
        show_staff = st.sidebar.checkbox("Статистика сотрудников", value=True)
        show_internet = st.sidebar.checkbox("Интернет-заявки", value=True)
        show_scripts = st.sidebar.checkbox("Выполнение скриптов", value=True)
        show_sales_funnel = st.sidebar.checkbox("Воронка продаж", value=True)
        show_reasons = st.sidebar.checkbox("Причины отказов", value=True)

        # Проверка структуры данных
        if df.shape[1] < 3:
            st.error("Неверная структура данных. Ожидается минимум 3 колонки.")
            return

        data_columns = df.columns[2:].tolist()
        max_day = len(data_columns)

        if max_day == 0:
            st.warning("В выбранном листе нет колонок с данными по дням.")
            return

        # Выбор диапазона дней
        start_day, end_day = st.select_slider(
            "Выберите диапазон дней",
            options=list(range(1, max_day + 1)),
            value=(1, min(5, max_day))
        )

        # Получение колонок для выбранного периода
        day_cols = data_columns[start_day - 1:end_day]

        # Нормализация названий колонок
        normalized_day_cols = [normalize_date(col) for col in day_cols]
        col_mapping = {normalize_date(col): col for col in df.columns[2:]}

        # Получение оригинальных названий колонок
        selected_cols = [col_mapping[col] for col in normalized_day_cols if col in col_mapping]

        if not selected_cols:
            st.error("Не удалось сопоставить выбранные даты с данными. Проверьте форматы дат в файле.")
            return

        # Обработка данных
        data_period, data_period_aggregated = process_data(df, selected_cols)

        if data_period_aggregated.empty:
            st.error("Не удалось обработать данные.")
            return

        # Обработка данных предыдущего месяца
        data_period_prev_aggregated = pd.DataFrame()
        if df_prev is not None:
            try:
                prev_col_mapping = {normalize_date(col): col for col in df_prev.columns[2:]}
                prev_selected_cols = [prev_col_mapping[col] for col in normalized_day_cols
                                      if col in prev_col_mapping]
                if prev_selected_cols:
                    _, data_period_prev_aggregated = process_data(df_prev, prev_selected_cols)
            except Exception as e:
                logger.warning(f"Ошибка обработки данных предыдущего месяца: {e}")

        st.success("Файл успешно загружен!")

        # Показ сравнения
        st.markdown(f'### Сравнение {selected_sheet} и {prev_sheet or "Нет данных"}')
        st.write(f"Текущий период (дни {start_day}-{end_day}): показатели рассчитаны")

        if not data_period_prev_aggregated.empty:
            st.write("Данные предыдущего периода также загружены")

        # Ключевые метрики
        if show_metrics:
            st.markdown('<div class="section-header">📈 Ключевые показатели</div>', unsafe_allow_html=True)

            total_incoming = find_metric_value(data_period_aggregated, "Входящие звонки - ВЗ")
            total_accepted = find_metric_value(data_period_aggregated, "Принятые ВЗ")
            total_missed = find_metric_value(data_period_aggregated, "Непринятые ВЗ")

            acceptance_rate = round((total_accepted / total_incoming * 100), 1) if total_incoming > 0 else 0

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)

            with col_m1:
                st.markdown(create_metric_card("Всего входящих", f"{int(total_incoming)}"), unsafe_allow_html=True)
            with col_m2:
                st.markdown(create_metric_card("Принято звонков", f"{int(total_accepted)}"), unsafe_allow_html=True)
            with col_m3:
                st.markdown(create_metric_card("Процент принятых", f"{acceptance_rate}%"), unsafe_allow_html=True)
            with col_m4:
                st.markdown(create_metric_card("Пропущено", f"{int(total_missed)}"), unsafe_allow_html=True)

            # Дополнительные метрики
            target_ads_spend = find_metric_value(data_period_aggregated, "Траты на таргет")
            leads = find_metric_value(data_period_aggregated, "Лиды \\(ИЗ\\)")
            visits = find_metric_value(data_period_aggregated, "Визиты")
            deliveries = find_metric_value(data_period_aggregated, "Выдачи")

            cost_per_lead = target_ads_spend / leads if leads > 0 else 0
            cost_per_visit = target_ads_spend / visits if visits > 0 else 0
            cost_per_delivery = target_ads_spend / deliveries if deliveries > 0 else 0

            col_tar1, col_tar2, col_tar3, col_tar4 = st.columns(4)
            with col_tar1:
                st.markdown(create_metric_card("Траты на таргет", f"{target_ads_spend:,.0f}₸"), unsafe_allow_html=True)
            with col_tar2:
                st.markdown(create_metric_card("Стоимость лида (ИЗ)", f"{cost_per_lead:,.0f}₸"), unsafe_allow_html=True)
            with col_tar3:
                st.markdown(create_metric_card("Стоимость визита", f"{cost_per_visit:,.0f}₸"), unsafe_allow_html=True)
            with col_tar4:
                st.markdown(create_metric_card("Стоимость выдачи", f"{cost_per_delivery:,.0f}₸"),
                            unsafe_allow_html=True)

        # Предпросмотр данных
        if show_data_preview:
            st.markdown('<div class="section-header">📋 Предпросмотр данных</div>', unsafe_allow_html=True)
            st.dataframe(df, use_container_width=True)

        # Создание графиков
        graphs = {}

        if show_dynamics:
            graphs['dynamics'] = create_dynamics_chart(data_period, selected_cols, start_day, end_day)

        if show_funnel:
            graphs['funnel'] = create_funnel_chart(data_period_aggregated, start_day, end_day)

        if show_staff:
            fig_staff, fig_pie = create_staff_charts(data_period_aggregated, start_day, end_day)
            if fig_staff:
                graphs['staff'] = fig_staff
            if fig_pie:
                graphs['staff_pie'] = fig_pie

        if show_internet:
            graphs['internet'] = create_internet_chart(data_period_aggregated, start_day, end_day)

        if show_scripts:
            # Убедитесь, что selected_cols определен в этом месте кода!
            graphs['scripts'] = create_scripts_chart(data_period, selected_cols, start_day, end_day)

        if show_sales_funnel:
            graphs['sales_funnel'] = create_sales_funnel_chart(data_period_aggregated, start_day, end_day)

        if show_reasons:
            graphs['reasons'] = create_reasons_chart(df, data_period_aggregated, start_day, end_day)

        # Отображение графиков
        if graphs.get('dynamics') or graphs.get('funnel'):
            col1, col2 = st.columns([2, 1])
            if graphs.get('dynamics'):
                with col1:
                    st.plotly_chart(graphs['dynamics'], use_container_width=True)
            if graphs.get('funnel'):
                with col2:
                    st.plotly_chart(graphs['funnel'], use_container_width=True)

        if graphs.get('staff') or graphs.get('staff_pie'):
            col3, col4 = st.columns([1, 1])
            if graphs.get('staff'):
                with col3:
                    st.plotly_chart(graphs['staff'], use_container_width=True)
            if graphs.get('staff_pie'):
                with col4:
                    st.plotly_chart(graphs['staff_pie'], use_container_width=True)

        if graphs.get('internet') or graphs.get('scripts'):
            col5, col6 = st.columns([1, 1])
            if graphs.get('internet'):
                with col5:
                    st.plotly_chart(graphs['internet'], use_container_width=True)
            if graphs.get('scripts'):
                with col6:
                    st.plotly_chart(graphs['scripts'], use_container_width=True)

        if graphs.get('sales_funnel') or graphs.get('reasons'):
            col7, col8 = st.columns([1, 1])
            if graphs.get('sales_funnel'):
                with col7:
                    st.plotly_chart(graphs['sales_funnel'], use_container_width=True)
            if graphs.get('reasons'):
                with col8:
                    st.plotly_chart(graphs['reasons'], use_container_width=True)

    except Exception as e:
        logger.error(f"Ошибка в основном приложении: {e}")
        st.error(f"Произошла ошибка: {str(e)}")


if __name__ == "__main__":
    main()
