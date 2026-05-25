import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Fix Lỗi Cột Đình)")

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

def get_greenhouse_advice(vpd, stage, safe_min, safe_max):
    if pd.isna(vpd):
        return "N/A", "Chờ dữ liệu...", "#808080"
    if vpd < 0.8:
        return "🔵 QUÁ THẤP", "Độ ẩm cao, nguy cơ nấm bệnh!", "#1E90FF"
    if 0.8 <= vpd <= 1.2:
        return "🟢 LÝ TƯỞNG", "Cây phát triển cực tốt.", "#00C851"
    if 1.2 < vpd <= 1.5:
        return "🟡 CẢNH BÁO", "VPD hơi cao, theo dõi sát.", "#FFA500"
    if vpd > 1.5:
        return "🔴 QUÁ CAO", "Stress nhiệt nặng!", "#FF4B4B"
    return "🟡 CẢNH BÁO", "Kiểm tra môi trường.", "#FFA500"

# --- XỬ LÝ DỮ LIỆU & KHỬ NHIỄU MẠNH ---
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

    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols:
        df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols:
        df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]

    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')

            # Xử lý đơn vị độ F và lọc rác cơ bản
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5 / 9
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan
            if col == 'humi':
                df.loc[(df[col] < 5) | (df[col] > 100), col] = np.nan

    # --- LOGIC KHỬ "CỘT ĐÌNH" (NHIỄU NHẢY VỌT) ---
    df = df.dropna(subset=['temp', 'humi']).copy()
    if len(df) > 5:
        for c in ['temp', 'humi']:
            diff = df[c].diff().abs()
            df.loc[diff > 7, c] = np.nan
            df[c] = df[c].interpolate(method='linear').ffill().bfill()

    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- SIDEBAR ---
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()
    uploaded_file = st.file_uploader("Tải file JSON", type=['json'])

if uploaded_file:
    df = process_data(uploaded_file)
    if not df.empty:
        st.sidebar.header("🔍 Lọc dữ liệu")
        df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
        filter_mode = st.sidebar.radio("Lọc:", ["Tất cả", "Tháng", "Khoảng ngày"])

        if filter_mode == "Tháng":
            sel_m = st.sidebar.multiselect("Tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        st.sidebar.divider()
        growth_stage = st.sidebar.radio("Giai đoạn:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm:", stt_list)
        if sel_stt != "Tất cả":
            df_work = df_work[df_work['STT'] == sel_stt]

        st.sidebar.divider()
        if "Cây con" in growth_stage:
            def_val = (0.4, 0.8)
        elif "Sinh trưởng" in growth_stage:
            def_val = (0.8, 1.2)
        else:
            def_val = (1.2, 1.5)
        safe_range = st.sidebar.slider("🎚️ Khoảng an toàn VPD", 0.0, 3.0, def_val, 0.1)
        safe_min, safe_max = safe_range

        # --- HIỂN THỊ ---
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage, safe_min, safe_max)

            st.subheader("📍 Thông số trạm")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")

            html_box = f'<div style="background-color:{color}; padding:15px; border-radius:10px; color:white; text-align:center;"><h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
            m2.markdown(html_box, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo:** {advice}")

            if "🔴" in status or "🔵" in status:
                if st.button("📧 Gửi Email"):
                    if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                        st.success("✅ Đã gửi!")
                    else:
                        st.error("❌ Lỗi Gmail!")

            # BIỂU ĐỒ DIỄN BIẾN
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)

            # Trace VPD
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green', width=3)), row=1, col=1)

            # Dải màu VPD — đỏ từ 1.5 trở lên
            fig.add_hrect(y0=0,   y1=0.8, fillcolor="rgba(30, 144, 255, 0.4)", line_width=0, row=1, col=1)  # xanh dương: quá thấp
            fig.add_hrect(y0=0.8, y1=1.2, fillcolor="rgba(0, 200, 81, 0.4)",   line_width=0, row=1, col=1)  # xanh lá: lý tưởng
            fig.add_hrect(y0=1.2, y1=1.5, fillcolor="rgba(255, 165, 0, 0.4)",  line_width=0, row=1, col=1)  # cam: cảnh báo
            fig.add_hrect(y0=1.5, y1=3.0, fillcolor="rgba(255, 75, 75, 0.4)",  line_width=0, row=1, col=1)  # đỏ: quá cao

            # Trace Temp & Humi
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)

            fig.update_layout(height=550, margin=dict(l=20, r=20, t=20, b=20), template="plotly_white", hovermode='x unified')
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("📋 Thống kê")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))

            def highlight_alert(row):
                if row['VPD'] > 1.5:
                    return ['background-color: #FFC7CE'] * len(row)
                if 1.2 < row['VPD'] <= 1.5:
                    return ['background-color: #FFE0B2'] * len(row)
                if row['VPD'] < 0.8:
                    return ['background-color: #D6EAF8'] * len(row)
                return [''] * len(row)

            styled_df = df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False).style.apply(highlight_alert, axis=1)
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.error("🚨 Không có dữ liệu.")
else:
    st.info("👈 Tải file JSON để xem.")
