import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    if vpd > 1.5:
        ly_do, tinh_trang = "Nóng và khô quá mức.", "Cây cháy lá, héo rũ."
        cach_xu_ly = "Bật phun sương, kéo rèm che nắng ngay."
    elif vpd < 0.8:
        ly_do, tinh_trang = "Độ ẩm quá cao.", "Nguy cơ thối rễ, nấm bệnh."
        cach_xu_ly = "Bật quạt thông gió, ngừng tưới."
    else:
        ly_do, tinh_trang, cach_xu_ly = "Bình thường.", "Cây ổn định.", "Tiếp tục theo dõi."
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"🚨 CẢNH BÁO VPD: {status}"
        body = f"📍 TRẠNG THÁI: {status}\nVPD: {vpd} kPa\nNhiệt độ: {temp}°C\nĐộ ẩm: {humi}%\n\nLý do: {ly_do}\nTình trạng: {tinh_trang}\nXử lý: {cach_xu_ly}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except:
        return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi):
        return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# --- NGƯỠNG VPD THEO TỪNG LOẠI CÂY ---
CROP_VPD = {
    "🌶️ Ớt chuông": {
        "low": 0.6, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5,
        "note_low":  "Ớt chuông dễ nấm xám khi ẩm cao.",
        "note_ok":   "Ớt chuông phát triển tốt, tiếp tục duy trì.",
        "note_warn": "Hơi khô, kiểm tra hệ thống tưới phun.",
        "note_high": "Stress nhiệt, ớt dễ rụng hoa và quả non.",
    },
    "🥒 Dưa leo": {
        "low": 0.7, "ideal_min": 0.9, "ideal_max": 1.3, "warn_max": 1.6,
        "note_low":  "Dưa leo dễ bị phấn trắng khi độ ẩm quá cao.",
        "note_ok":   "Dưa leo sinh trưởng tốt, giữ nguyên điều kiện.",
        "note_warn": "VPD hơi cao, tăng phun sương nhẹ.",
        "note_high": "Dưa leo héo nhanh, cần tưới và che nắng gấp.",
    },
    "🍈 Dưa lưới": {
        "low": 0.8, "ideal_min": 1.0, "ideal_max": 1.4, "warn_max": 1.8,
        "note_low":  "Dưa lưới cần thoáng, ẩm cao gây nứt quả.",
        "note_ok":   "Dưa lưới trong ngưỡng lý tưởng.",
        "note_warn": "Kiểm tra hệ thống thông gió, VPD đang cao dần.",
        "note_high": "Stress nước nghiêm trọng, dưa lưới dễ nứt vỏ.",
    },
    "🍅 Cà chua": {
        "low": 0.7, "ideal_min": 0.8, "ideal_max": 1.2, "warn_max": 1.5,
        "note_low":  "Cà chua dễ bị mốc sương khi độ ẩm quá cao.",
        "note_ok":   "Cà chua phát triển tốt, hoa đậu quả bình thường.",
        "note_warn": "VPD cao, cà chua có thể rụng hoa.",
        "note_high": "Stress nhiệt nặng, cà chua ngừng đậu quả.",
    },
}

def get_greenhouse_advice(vpd, crop):
    if pd.isna(vpd):
        return "N/A", "Chờ dữ liệu...", "#808080"
    c = CROP_VPD.get(crop, list(CROP_VPD.values())[0])
    lo, i_min, i_max, w_max = c["low"], c["ideal_min"], c["ideal_max"], c["warn_max"]
    if vpd < lo:
        return "🔵 QUÁ THẤP",  c["note_low"],  "#1E90FF"
    if lo <= vpd < i_min:
        return "🟡 CẢNH BÁO",  c["note_warn"], "#FFA500"
    if i_min <= vpd <= i_max:
        return "🟢 LÝ TƯỞNG",  c["note_ok"],   "#00C851"
    if i_max < vpd <= w_max:
        return "🟡 CẢNH BÁO",  c["note_warn"], "#FFA500"
    return "🔴 QUÁ CAO",       c["note_high"], "#FF4B4B"

# --- XỬ LÝ DỮ LIỆU & KHỬ NHIỄU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except:
        return pd.DataFrame()

    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(
            df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'),
            errors='coerce', utc=True
        ).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')

    df['temp'] = np.nan
    df['humi'] = np.nan

    if 'tempKK' in df.columns:
        mask = df['tempKK'].notna()
        val = pd.to_numeric(df.loc[mask, 'tempKK'], errors='coerce')
        df.loc[mask, 'temp'] = np.where(val > 45, (val - 32) * 5 / 9, val)

    if 'humiKK' in df.columns:
        mask = df['humiKK'].notna()
        df.loc[mask, 'humi'] = pd.to_numeric(df.loc[mask, 'humiKK'], errors='coerce')

    if 'Nhiệt Độ' in df.columns:
        mask = df['Nhiệt Độ'].notna() & df['temp'].isna()
        val = pd.to_numeric(df.loc[mask, 'Nhiệt Độ'], errors='coerce')
        df.loc[mask, 'temp'] = val / 10

    if 'Độ ẩm' in df.columns:
        mask = df['Độ ẩm'].notna() & df['humi'].isna()
        val = pd.to_numeric(df.loc[mask, 'Độ ẩm'], errors='coerce')
        df.loc[mask, 'humi'] = val / 10

    df.loc[(df['temp'] < 5) | (df['temp'] > 55), 'temp'] = np.nan
    df.loc[(df['humi'] < 5) | (df['humi'] > 100), 'humi'] = np.nan

    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            diff = df[c].diff().abs()
            df.loc[diff > 7, c] = np.nan
            df[c] = df[c].interpolate(method='linear').ffill().bfill()

    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- HÀM VẼ BIỂU ĐỒ DÙNG CHUNG ---
def draw_chart(df_valid, c_info, smooth=True):
    df_chart = df_valid.copy()
    x_col = 'Thời gian'

    if smooth and 'Thời gian' in df_chart.columns and not df_chart['Thời gian'].isna().all() and len(df_chart) > 10:
        df_chart = df_chart.set_index('Thời gian')
        for col in ['VPD', 'temp', 'humi']:
            if col in df_chart.columns:
                q1 = df_chart[col].quantile(0.05)
                q3 = df_chart[col].quantile(0.95)
                iqr = q3 - q1
                df_chart.loc[(df_chart[col] < q1 - 2.5*iqr) | (df_chart[col] > q3 + 2.5*iqr), col] = np.nan
        df_chart = df_chart.resample('1h').agg({'VPD': 'median', 'temp': 'median', 'humi': 'median'}).dropna(how='all')
        df_chart['VPD']  = df_chart['VPD'].rolling(3, center=True, min_periods=1).mean()
        df_chart['temp'] = df_chart['temp'].rolling(3, center=True, min_periods=1).mean()
        df_chart['humi'] = df_chart['humi'].rolling(3, center=True, min_periods=1).mean()
        df_chart = df_chart.reset_index()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("VPD (kPa)", "Nhiệt độ & Độ ẩm"))

    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['VPD'].round(2),
        name="VPD (kPa)", line=dict(color='#2E7D32', width=2.5), mode='lines'
    ), row=1, col=1)

    vpd_max = float(max(df_chart['VPD'].max() * 1.15, 3.5)) if not df_chart.empty else 3.5
    c_lo, c_imin, c_imax, c_wmax = c_info["low"], c_info["ideal_min"], c_info["ideal_max"], c_info["warn_max"]
    fig.add_hrect(y0=0,      y1=c_lo,    fillcolor="rgba(30, 144, 255, 0.35)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_lo,   y1=c_imin,  fillcolor="rgba(255, 165, 0, 0.35)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imin, y1=c_imax,  fillcolor="rgba(0, 200, 81, 0.35)",   line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imax, y1=c_wmax,  fillcolor="rgba(255, 165, 0, 0.35)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_wmax, y1=vpd_max, fillcolor="rgba(255, 75, 75, 0.35)",  line_width=0, row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['temp'].round(1),
        name="Nhiệt độ (°C)", line=dict(color='#E53935', width=2), mode='lines'
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['humi'].round(1),
        name="Độ ẩm (%)", line=dict(color='#1E88E5', width=2), mode='lines'
    ), row=2, col=1)

    fig.update_layout(
        height=520, margin=dict(l=20, r=20, t=30, b=20),
        template="plotly_white", hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )
    fig.update_yaxes(title_text="kPa", row=1, col=1)
    fig.update_yaxes(title_text="°C / %", row=2, col=1)
    return fig

# --- HÀM HIỂN THỊ METRIC CARD ---
def show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop):
    st.subheader("📍 Thông số mới nhất")
    m1, m2, m3 = st.columns([1, 1.2, 1.8])
    m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
    m1.metric("Độ ẩm",    f"{round(last['humi'], 1)} %")
    html_box = (f'<div style="background-color:{color};padding:15px;border-radius:10px;'
                f'color:white;text-align:center;">'
                f'<h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>')
    m2.markdown(html_box, unsafe_allow_html=True)
    m3.warning(f"**Chỉ đạo:** {advice}")
    if "🔴" in status or "🔵" in status:
        if st.button("📧 Gửi Email cảnh báo"):
            if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                st.success("✅ Đã gửi!")
            else:
                st.error("❌ Lỗi Gmail!")

# =========================================================
# --- SIDEBAR ---
# =========================================================
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()

    # --- CHỌN CHẾ ĐỘ ---
    st.header("⚙️ Chế độ")
    mode = st.radio("", ["📂 Xem file JSON", "🔴 Realtime (90 giây)"], index=0)
    st.divider()

    crop_names = list(CROP_VPD.keys())
    selected_crop = st.selectbox("🌱 Loại cây:", crop_names, index=0)
    c_info = CROP_VPD[selected_crop]
    st.caption(
        f"Ngưỡng lý tưởng: **{c_info['ideal_min']} – {c_info['ideal_max']} kPa**  \n"
        f"Cảnh báo: > {c_info['warn_max']} kPa"
    )
    st.divider()

    if mode == "📂 Xem file JSON":
        uploaded_file = st.file_uploader("Tải file JSON", type=['json'])
    else:
        rt_source = st.radio("Nguồn dữ liệu:", ["🎲 Mô phỏng", "📡 API thật"], index=0)
        if rt_source == "📡 API thật":
            api_url = st.text_input("URL API:", placeholder="http://192.168.x.x/data")
        else:
            api_url = ""
            st.caption("Dữ liệu nhiệt độ & độ ẩm sẽ được sinh ngẫu nhiên có dao động thực tế.")
        rt_running = st.toggle("▶️ Bật Realtime", value=False)
        rt_window  = st.slider("Hiển thị N điểm gần nhất", 20, 200, 60, 10)

# =========================================================
# --- CHẾ ĐỘ XEM FILE ---
# =========================================================
if mode == "📂 Xem file JSON":
    if uploaded_file:
        df = process_data(uploaded_file)
        if not df.empty:
            df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
            with st.sidebar:
                filter_mode = st.radio("Lọc:", ["Tất cả", "Tháng", "Khoảng ngày"])
                if filter_mode == "Tháng":
                    sel_m = st.multiselect("Tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
                    df_work = df[df['Tháng'].isin(sel_m)].copy()
                elif filter_mode == "Khoảng ngày":
                    c1, c2 = st.columns(2)
                    start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
                    end   = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
                    df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
                else:
                    df_work = df.copy()
                stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
                sel_stt  = st.selectbox("📍 Chọn Trạm:", stt_list)
                if sel_stt != "Tất cả":
                    df_work = df_work[df_work['STT'] == sel_stt]

            df_valid = df_work.dropna(subset=['VPD'])
            if not df_valid.empty:
                last = df_valid.iloc[-1]
                status, advice, color = get_greenhouse_advice(last['VPD'], selected_crop)
                show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop)
                st.plotly_chart(draw_chart(df_valid, c_info, smooth=True), use_container_width=True)

                st.subheader("📋 Thống kê")
                st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))

                def highlight_alert(row):
                    if row['VPD'] > c_info['warn_max']:      return ['background-color: #FFC7CE'] * len(row)
                    if row['VPD'] > c_info['ideal_max']:     return ['background-color: #FFE0B2'] * len(row)
                    if row['VPD'] < c_info['low']:           return ['background-color: #D6EAF8'] * len(row)
                    return [''] * len(row)

                styled_df = (df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                             .sort_values('Thời gian', ascending=False)
                             .style.apply(highlight_alert, axis=1))
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.error("🚨 Không có dữ liệu hợp lệ.")
        else:
            st.error("🚨 Không đọc được file JSON.")
    else:
        st.info("👈 Tải file JSON để xem.")

# =========================================================
# --- CHẾ ĐỘ REALTIME ---
# =========================================================
else:
    REALTIME_INTERVAL = 90  # giây

    # Khởi tạo session state lưu lịch sử realtime
    if 'rt_history' not in st.session_state:
        st.session_state.rt_history = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD'])
    if 'rt_last_fetch' not in st.session_state:
        st.session_state.rt_last_fetch = 0
    if 'rt_error' not in st.session_state:
        st.session_state.rt_error = ""

    # --- Placeholder để cập nhật không bị re-render toàn trang ---
    status_bar   = st.empty()
    metric_area  = st.empty()
    chart_area   = st.empty()
    table_area   = st.empty()
    countdown_ph = st.empty()

    def fetch_and_append(url):
        """Gọi API, lấy dòng mới nhất, thêm vào lịch sử."""
        import urllib.request, json
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                raw = json.loads(r.read().decode())
        except Exception as e:
            return False, str(e)

        # raw có thể là list hoặc dict
        if isinstance(raw, list):
            row = raw[-1] if raw else {}
        elif isinstance(raw, dict):
            row = raw
        else:
            return False, "Định dạng API không nhận ra."

        # Đọc temp / humi tương tự process_data
        temp = humi = None
        if 'tempKK' in row:
            v = float(row['tempKK'])
            temp = (v - 32) * 5/9 if v > 45 else v
        elif 'Nhiệt Độ' in row:
            temp = float(row['Nhiệt Độ']) / 10

        if 'humiKK' in row:
            humi = float(row['humiKK'])
        elif 'Độ ẩm' in row:
            humi = float(row['Độ ẩm']) / 10

        if temp is None or humi is None:
            return False, "Không tìm thấy trường temp/humi trong response."
        if not (5 <= temp <= 55) or not (5 <= humi <= 100):
            return False, f"Giá trị ngoài ngưỡng: temp={temp}, humi={humi}"

        vpd = calculate_vpd(temp, humi)
        now = datetime.now().replace(microsecond=0)
        new_row = pd.DataFrame([{'Thời gian': now, 'temp': round(temp,2),
                                  'humi': round(humi,2), 'VPD': vpd}])
        st.session_state.rt_history = pd.concat(
            [st.session_state.rt_history, new_row], ignore_index=True
        )
        return True, ""

    def render_realtime(window):
        hist = st.session_state.rt_history.tail(window)
        if hist.empty:
            return
        last = hist.iloc[-1]
        status, advice, color = get_greenhouse_advice(last['VPD'], selected_crop)

        with metric_area.container():
            show_metrics(last, status, advice, color, u_mail, u_pass, t_mail, selected_crop)

        # Biểu đồ realtime — không resample (dữ liệu thưa), chỉ vẽ thẳng
        with chart_area.container():
            st.plotly_chart(draw_chart(hist, c_info, smooth=False), use_container_width=True)

        with table_area.container():
            st.subheader("📋 Lịch sử realtime")
            def hl(row):
                if row['VPD'] > c_info['warn_max']:  return ['background-color: #FFC7CE'] * len(row)
                if row['VPD'] > c_info['ideal_max']: return ['background-color: #FFE0B2'] * len(row)
                if row['VPD'] < c_info['low']:       return ['background-color: #D6EAF8'] * len(row)
                return [''] * len(row)
            styled = hist[::-1].style.apply(hl, axis=1)
            st.dataframe(styled, use_container_width=True)

    # --- HÀM SINH DỮ LIỆU MÔ PHỎNG ---
    def simulate_point():
        """Sinh 1 điểm nhiệt độ & độ ẩm mô phỏng có dao động thực tế."""
        hist = st.session_state.rt_history
        if hist.empty:
            # Điểm khởi đầu ngẫu nhiên hợp lý
            temp = round(np.random.uniform(22, 32), 2)
            humi = round(np.random.uniform(55, 75), 2)
        else:
            last_temp = hist.iloc[-1]['temp']
            last_humi = hist.iloc[-1]['humi']
            # Dao động nhỏ quanh giá trị trước (±0.3°C, ±1% humi) + xu hướng ngẫu nhiên nhẹ
            temp = round(np.clip(last_temp + np.random.normal(0, 0.3), 10, 45), 2)
            humi = round(np.clip(last_humi + np.random.normal(0, 1.0), 20, 95), 2)
        vpd = calculate_vpd(temp, humi)
        now = datetime.now().replace(microsecond=0)
        new_row = pd.DataFrame([{'Thời gian': now, 'temp': temp, 'humi': humi, 'VPD': vpd}])
        st.session_state.rt_history = pd.concat(
            [st.session_state.rt_history, new_row], ignore_index=True
        )

    # --- CHẠY REALTIME LOOP ---
    if not rt_running:
        st.info("⏸️ Bật toggle **▶️ Bật Realtime** ở sidebar để bắt đầu.")
        if not st.session_state.rt_history.empty:
            render_realtime(rt_window)
    else:
        use_sim = (rt_source == "🎲 Mô phỏng")
        if not use_sim and not api_url:
            st.warning("⚠️ Nhập URL API trước khi bật Realtime.")
        else:
            src_label = "🎲 Mô phỏng" if use_sim else f"📡 {api_url}"
            status_bar.success(f"🟢 Realtime ({src_label}) — cập nhật mỗi {REALTIME_INTERVAL}s")

            while rt_running:
                now_ts = time.time()
                elapsed = now_ts - st.session_state.rt_last_fetch

                if elapsed >= REALTIME_INTERVAL or st.session_state.rt_last_fetch == 0:
                    if use_sim:
                        simulate_point()
                        st.session_state.rt_error = ""
                    else:
                        ok, err = fetch_and_append(api_url)
                        st.session_state.rt_error = "" if ok else err
                    st.session_state.rt_last_fetch = time.time()

                if st.session_state.rt_error:
                    status_bar.error(f"❌ Lỗi fetch: {st.session_state.rt_error}")
                else:
                    status_bar.success(f"🟢 Realtime ({src_label}) — cập nhật mỗi {REALTIME_INTERVAL}s")

                render_realtime(rt_window)

                # Đếm ngược đến lần fetch tiếp theo
                remaining = int(REALTIME_INTERVAL - (time.time() - st.session_state.rt_last_fetch))
                for i in range(max(remaining, 0), 0, -1):
                    countdown_ph.caption(f"⏱️ Lần đọc tiếp theo sau: {i}s")
                    time.sleep(1)
                countdown_ph.caption("🔄 Đang lấy dữ liệu...")
