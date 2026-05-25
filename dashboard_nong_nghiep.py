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
st.title("🌿 Hệ Thống Giám Sát Nhà Kính (Bản Full Đầy Đủ)")

# --- HÀM GỬI EMAIL ---
def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status, temp, humi):
    if vpd > 1.5:
        ly_do, tinh_trang = "Nóng và khô quá mức.", "Cây cháy lá, héo rũ."
        cach_xu_ly = "Bật phun sương, kéo rèm che nắng ngay."
    elif vpd < 0.4:
        ly_do, tinh_trang = "Độ ẩm quá cao.", "Nguy cơ thối rễ, nấm bệnh."
        cach_xu_ly = "Bật quạt thông gió, ngừng tưới."
    else:
        ly_do, tinh_trang, cach_xu_ly = "Lệch ngưỡng.", "Cây stress nhẹ.", "Kiểm tra lại thiết bị."

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
    except: return False

# --- TÍNH VPD ---
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi): return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

def get_greenhouse_advice(vpd, stage, safe_min, safe_max):
    if pd.isna(vpd): return "N/A", "Chờ dữ liệu...", "#808080"
    if "Cây con" in stage: i_min, i_max = 0.4, 0.8
    elif "Sinh trưởng" in stage: i_min, i_max = 0.8, 1.2
    else: i_min, i_max = 1.2, 1.5
    
    # --- Đánh giá dựa trên Khoảng an toàn chốt từ thanh Range Slider ---
    if vpd < safe_min: return "🔴 QUÁ THẤP", "Nguy cơ nấm bệnh!", "#FF4B4B"
    if i_min <= vpd <= i_max: return "🟢 LÝ TƯỞNG", "Cây phát triển tốt.", "#00C851"
    if vpd > safe_max: return "🔴 QUÁ CAO", "Stress nhiệt nặng!", "#8B0000"
    return "🟡 HƠI LỆCH", "Cần điều chỉnh nhẹ.", "#FFA500"

# --- XỬ LÝ DỮ LIỆU ---
def process_data(file):
    try:
        df = pd.read_json(file)
    except: return pd.DataFrame()
    if 'Thời gian' in df.columns:
        df['Thời gian'] = pd.to_datetime(df['Thời gian'].astype(str).str.replace('-', ' ', n=2).str.replace('-', ':'), errors='coerce', utc=True).dt.tz_localize(None)
        df = df.dropna(subset=['Thời gian']).sort_values('Thời gian')
    
    t_cols = [c for c in ['Nhiệt Độ', 'tempKK'] if c in df.columns]
    if t_cols: df['temp'] = df[t_cols].bfill(axis=1).iloc[:, 0]
    h_cols = [c for c in ['Độ ẩm', 'humiKK'] if c in df.columns]
    if h_cols: df['humi'] = df[h_cols].bfill(axis=1).iloc[:, 0]
    
    for col in ['temp', 'humi']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.extract(r'(\d+\.?\d*)')[0], errors='coerce')
            if col == 'temp':
                df.loc[df[col] > 150, col] = df[col] / 10 
                df.loc[(df[col] >= 45) & (df[col] <= 120), col] = (df[col] - 32) * 5/9 
                df.loc[(df[col] < 5) | (df[col] > 55), col] = np.nan 
            if col == 'humi':
                df.loc[(df[col] < 20) | (df[col] > 100), col] = np.nan 
    df = df.dropna(subset=['temp', 'humi']).copy()
    
    # --- FIX LỖI "LÊN CAO ĐỘT NGỘT" ---
    if len(df) > 2:
        df['temp'] = df['temp'].rolling(window=3, center=True, min_periods=1).median()
        df['humi'] = df['humi'].rolling(window=3, center=True, min_periods=1).median()
    # -----------------------------------
    
    if not df.empty: df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# --- SIDEBAR: CẤU HÌNH & BỘ LỌC ---
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
        
        filter_mode = st.sidebar.radio("Chế độ lọc thời gian:", ["Tất cả", "Tháng", "Khoảng ngày"])
        
        if filter_mode == "Tháng":
            sel_m = st.sidebar.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
            df_work = df[df['Tháng'].isin(sel_m)].copy()
        elif filter_mode == "Khoảng ngày":
            c1, c2 = st.sidebar.columns(2)
            start = pd.to_datetime(c1.date_input("Từ ngày", df['Thời gian'].min()))
            end = pd.to_datetime(c2.date_input("Đến ngày", df['Thời gian'].max())) + timedelta(days=1)
            df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
        else:
            df_work = df.copy()

        st.sidebar.divider()
        growth_stage = st.sidebar.radio("Giai đoạn cây:", ["🌱 Cây con", "🌿 Sinh trưởng", "🍅 Ra hoa"], index=1)
        stt_list = ["Tất cả"] + sorted(df_work['STT'].unique().tolist())
        sel_stt = st.sidebar.selectbox("📍 Chọn Trạm (STT):", stt_list)
        if sel_stt != "Tất cả": df_work = df_work[df_work['STT'] == sel_stt]

        # --- 1 THANH KÉO (RANGE SLIDER) CÓ 2 ĐẦU ---
        st.sidebar.divider()
        
        # Mặc định theo giai đoạn để thanh kéo tự động nảy số chuẩn
        if "Cây con" in growth_stage: def_val = (0.2, 1.1)
        elif "Sinh trưởng" in growth_stage: def_val = (0.5, 1.5)
        else: def_val = (0.9, 1.8)

        safe_range = st.sidebar.slider(
            "🎚️ Chỉnh khoảng an toàn VPD",
            min_value=0.0,
            max_value=3.0,
            value=def_val,
            step=0.1
        )
        safe_min, safe_max = safe_range

        # --- HIỂN THỊ DỮ LIỆU ---
        df_valid = df_work.dropna(subset=['VPD'])
        if not df_valid.empty:
            last = df_valid.iloc[-1]
            
            # Đẩy min/max của khoảng an toàn vào hàm để đánh giá trạng thái
            status, advice, color = get_greenhouse_advice(last['VPD'], growth_stage, safe_min, safe_max)
            
            st.subheader("📍 Trạng thái trạm đo")
            m1, m2, m3 = st.columns([1, 1.2, 1.8])
            m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
            m1.metric("Độ ẩm", f"{round(last['humi'], 1)} %")
            
            html_box = f'<div style="background-color:{color}; padding:15px; border-radius:10px; color:white; text-align:center;"><h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
            m2.markdown(html_box, unsafe_allow_html=True)
            m3.warning(f"**Chỉ đạo:** {advice}")

            if "🔴" in status:
                if st.button("📧 Gửi Email Cảnh Báo Khẩn"):
                    if send_email_alert(u_mail, u_pass, t_mail, last['VPD'], status, last['temp'], last['humi']):
                        st.success("✅ Đã gửi báo cáo chi tiết!")
                    else: st.error("❌ Kiểm tra cấu hình Gmail!")

            # BIỂU ĐỒ
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['VPD'], name="VPD (kPa)", line=dict(color='green')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['temp'], name="Nhiệt độ (°C)"), row=2, col=1)
            fig.add_trace(go.Scatter(x=df_valid['Thời gian'], y=df_valid['humi'], name="Độ ẩm (%)"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # THỐNG KÊ
            st.subheader("📋 Thống kê chi tiết")
            st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))
            
            # --- PHẦN NHUỘM MÀU BẢNG DỮ LIỆU ---
            def highlight_alert(row):
                # Báo đỏ nếu văng khỏi dải Range Slider
                if row['VPD'] < safe_min or row['VPD'] > safe_max:
                    return ['background-color: #FFC7CE; color: #9C0006; font-weight: bold'] * len(row)
                return [''] * len(row)

            # Áp dụng style vào dataframe
            styled_df = df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']].sort_values('Thời gian', ascending=False).style.apply(highlight_alert, axis=1)
            
            st.dataframe(styled_df, use_container_width=True)
            
        else:
            st.error("🚨 Không tìm thấy dữ liệu trong khoảng thời gian/trạm đã chọn.")
else:
    st.info("👈 Hãy nhập Gmail và tải file JSON ở thanh bên trái.")
