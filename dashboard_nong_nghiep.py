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

# =========================================================
# --- CẤU HÌNH TRANG ---
# =========================================================
st.set_page_config(page_title="Greenhouse Pro Max", layout="wide")
st.title("🌿 Hệ Thống Giám Sát Nhà Kính")

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

# =========================================================
# --- HÀM TÍNH VPD ---
# =========================================================
def calculate_vpd(temp, humi):
    if pd.isna(temp) or pd.isna(humi):
        return None
    vpsat = 0.61078 * np.exp((17.27 * temp) / (temp + 237.3))
    vpair = vpsat * (humi / 100)
    return round(vpsat - vpair, 2)

# =========================================================
# --- HÀM GỬI EMAIL CHI TIẾT ---
# =========================================================
def build_email_body(vpd, status, temp, humi, crop, df_history=None, source="Realtime"):
    c = CROP_VPD.get(crop, list(CROP_VPD.values())[0])
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    if vpd > c["warn_max"]:
        muc_do      = "🔴 NGUY HIỂM — VPD QUÁ CAO"
        nguyen_nhan = "Nhiệt độ quá cao hoặc độ ẩm quá thấp khiến cây mất nước nhanh chóng qua lỗ khí khổng."
        hau_qua     = "Cây bị stress nước nặng, lỗ khí khổng đóng lại → quang hợp giảm → héo, rụng hoa/quả non."
        xu_ly       = (
            "1. Bật hệ thống phun sương ngay lập tức.\n"
            "2. Kéo rèm che nắng / lưới lan để giảm bức xạ nhiệt.\n"
            "3. Kiểm tra quạt thông gió — đảm bảo lưu thông khí.\n"
            "4. Tăng tần suất tưới nhỏ giọt (giảm chu kỳ 30–50%).\n"
            f"5. Theo dõi lại sau 30 phút; nếu VPD > {c['warn_max']:.1f} kPa liên tục → kiểm tra bơm phun."
        )
    elif vpd > c["ideal_max"]:
        muc_do      = "🟡 CẢNH BÁO — VPD HƠI CAO"
        nguyen_nhan = "Độ ẩm đang giảm dần hoặc nhiệt độ tăng nhẹ so với ngưỡng lý tưởng."
        hau_qua     = "Cây bắt đầu căng thẳng nhẹ, năng suất và chất lượng hoa quả có thể bị ảnh hưởng."
        xu_ly       = (
            "1. Tăng nhẹ phun sương (tăng tần suất 15–20%).\n"
            "2. Kiểm tra rèm che — cân nhắc che bổ sung vào giờ cao điểm nắng.\n"
            "3. Theo dõi xu hướng: nếu VPD tiếp tục tăng, bật phun sương liên tục."
        )
    elif vpd < c["low"]:
        muc_do      = "🔵 NGUY HIỂM — VPD QUÁ THẤP"
        nguyen_nhan = "Độ ẩm không khí quá cao, cây không thoát được hơi nước qua lỗ khí khổng."
        hau_qua     = "Nguy cơ nấm bệnh (thối xám, phấn trắng, mốc), rễ yếu, lá vàng úa và thối nhũn."
        xu_ly       = (
            "1. Bật quạt thông gió ngay — tăng tốc độ tối đa.\n"
            "2. Ngừng toàn bộ hệ thống tưới phun.\n"
            "3. Mở cửa thông gió (nếu có) để trao đổi khí với bên ngoài.\n"
            "4. Kiểm tra hệ thống thoát nước — tránh đọng nước trên lá.\n"
            "5. Cân nhắc phun thuốc phòng nấm nếu tình trạng kéo dài > 2 giờ."
        )
    elif vpd < c["ideal_min"]:
        muc_do      = "🟡 CẢNH BÁO — VPD HƠI THẤP"
        nguyen_nhan = "Độ ẩm đang ở mức hơi cao, tiếp cận ngưỡng nguy hiểm."
        hau_qua     = "Thoát hơi nước của cây kém, môi trường thuận lợi cho nấm bệnh phát triển."
        xu_ly       = (
            "1. Tăng tốc độ quạt thông gió 20–30%.\n"
            "2. Giảm lượng tưới trong chu kỳ tiếp theo.\n"
            "3. Theo dõi sát — nếu VPD tiếp tục giảm, ngừng tưới hoàn toàn."
        )
    else:
        muc_do      = "🟢 BÌNH THƯỜNG"
        nguyen_nhan = "Điều kiện môi trường đang trong ngưỡng lý tưởng cho loại cây này."
        hau_qua     = "Cây phát triển tốt, trao đổi chất hiệu quả."
        xu_ly       = "Tiếp tục duy trì điều kiện hiện tại. Theo dõi định kỳ."

    stats_block = ""
    if df_history is not None and len(df_history) >= 3:
        recent = df_history.tail(12)
        stats_block = (
            f"\n📊 THỐNG KÊ 3 GIỜ GẦN NHẤT ({len(recent)} điểm đo):\n"
            f"   Nhiệt độ : Min {recent['temp'].min():.1f}°C  |  Max {recent['temp'].max():.1f}°C  |  TB {recent['temp'].mean():.1f}°C\n"
            f"   Độ ẩm    : Min {recent['humi'].min():.1f}%   |  Max {recent['humi'].max():.1f}%   |  TB {recent['humi'].mean():.1f}%\n"
            f"   VPD      : Min {recent['VPD'].min():.2f} kPa |  Max {recent['VPD'].max():.2f} kPa |  TB {recent['VPD'].mean():.2f} kPa\n"
        )

    nguong_block = (
        f"\n📐 NGƯỠNG VPD CÀI ĐẶT ({crop}):\n"
        f"   Quá thấp  : < {c['low']} kPa\n"
        f"   Cảnh báo  : {c['low']} – {c['ideal_min']} kPa\n"
        f"   Lý tưởng  : {c['ideal_min']} – {c['ideal_max']} kPa\n"
        f"   Cảnh báo  : {c['ideal_max']} – {c['warn_max']} kPa\n"
        f"   Quá cao   : > {c['warn_max']} kPa\n"
    )

    body = f"""
╔══════════════════════════════════════════════╗
   HỆ THỐNG GIÁM SÁT NHÀ KÍNH — CẢNH BÁO VPD
╚══════════════════════════════════════════════╝

🕐 Thời gian    : {now_str}
📡 Nguồn        : {source}
🌱 Loại cây     : {crop}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 THÔNG SỐ HIỆN TẠI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Nhiệt độ  : {temp:.1f} °C
   Độ ẩm     : {humi:.1f} %
   VPD       : {vpd:.2f} kPa

⚠️  MỨC ĐỘ    : {muc_do}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 PHÂN TÍCH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Nguyên nhân  : {nguyen_nhan}
Hậu quả      : {hau_qua}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛠️  HƯỚNG XỬ LÝ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{xu_ly}
{stats_block}{nguong_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Email tự động từ Hệ thống Giám sát Nhà Kính
Vui lòng không trả lời email này.
"""
    return body


def send_email_alert(sender_mail, app_password, receiver_mail, vpd, status,
                     temp, humi, crop, df_history=None, source="Realtime"):
    try:
        body = build_email_body(vpd, status, temp, humi, crop, df_history, source)
        msg = MIMEMultipart()
        msg['From']    = sender_mail
        msg['To']      = receiver_mail
        msg['Subject'] = f"🚨 [{source}] Cảnh báo VPD {status} — {vpd:.2f} kPa | {crop}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_mail, app_password)
        server.sendmail(sender_mail, receiver_mail, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# =========================================================
# --- HÀM ĐÁNH GIÁ VPD ---
# =========================================================
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

# =========================================================
# --- XỬ LÝ FILE JSON ---
# =========================================================
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

    # STT 5: tempKK (°F) → °C, humiKK (%)
    if 'tempKK' in df.columns:
        mask = df['tempKK'].notna()
        val  = pd.to_numeric(df.loc[mask, 'tempKK'], errors='coerce')
        df.loc[mask, 'temp'] = np.where(val > 45, (val - 32) * 5 / 9, val)

    if 'humiKK' in df.columns:
        mask = df['humiKK'].notna()
        df.loc[mask, 'humi'] = pd.to_numeric(df.loc[mask, 'humiKK'], errors='coerce')

    # STT 2, 3: Nhiệt Độ / Độ ẩm raw x10 → chia 10
    for col_name in ['Nhiệt Độ', 'Nhiệt độ']:
        if col_name in df.columns:
            mask = df[col_name].notna() & df['temp'].isna()
            df.loc[mask, 'temp'] = pd.to_numeric(df.loc[mask, col_name], errors='coerce') / 10

    if 'Độ ẩm' in df.columns:
        mask = df['Độ ẩm'].notna() & df['humi'].isna()
        df.loc[mask, 'humi'] = pd.to_numeric(df.loc[mask, 'Độ ẩm'], errors='coerce') / 10

    df.loc[(df['temp'] < 5)  | (df['temp'] > 55),  'temp'] = np.nan
    df.loc[(df['humi'] < 5)  | (df['humi'] > 100), 'humi'] = np.nan
    df = df.dropna(subset=['temp', 'humi']).copy()

    if len(df) > 5:
        for c in ['temp', 'humi']:
            diff = df[c].diff().abs()
            df.loc[diff > 7, c] = np.nan
            df[c] = df[c].interpolate(method='linear').ffill().bfill()

    if not df.empty:
        df['VPD'] = df.apply(lambda r: calculate_vpd(r['temp'], r['humi']), axis=1)
    return df

# =========================================================
# --- HÀM VẼ BIỂU ĐỒ ---
# =========================================================
def draw_chart(df_valid, c_info, smooth=True, x_label="Thời gian"):
    df_chart = df_valid.copy()
    x_col    = 'Thời gian'

    if smooth and x_col in df_chart.columns and len(df_chart) > 10:
        df_chart = df_chart.set_index(x_col)
        for col in ['VPD', 'temp', 'humi']:
            if col in df_chart.columns:
                q1  = df_chart[col].quantile(0.05)
                q3  = df_chart[col].quantile(0.95)
                iqr = q3 - q1
                df_chart.loc[(df_chart[col] < q1 - 2.5*iqr) | (df_chart[col] > q3 + 2.5*iqr), col] = np.nan
        df_chart = df_chart.resample('1h').agg({'VPD': 'median', 'temp': 'median', 'humi': 'median'}).dropna(how='all')
        df_chart['VPD']  = df_chart['VPD'].rolling(3, center=True, min_periods=1).mean()
        df_chart['temp'] = df_chart['temp'].rolling(3, center=True, min_periods=1).mean()
        df_chart['humi'] = df_chart['humi'].rolling(3, center=True, min_periods=1).mean()
        df_chart = df_chart.reset_index()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
        subplot_titles=("VPD (kPa)", "Nhiệt độ & Độ ẩm")
    )

    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['VPD'].round(2),
        name="VPD (kPa)", line=dict(color='#2E7D32', width=2.5),
        mode='lines+markers', marker=dict(size=4)
    ), row=1, col=1)

    vpd_max = float(max(df_chart['VPD'].dropna().max() * 1.15, 3.5)) if not df_chart.empty else 3.5
    c_lo, c_imin, c_imax, c_wmax = c_info["low"], c_info["ideal_min"], c_info["ideal_max"], c_info["warn_max"]

    fig.add_hrect(y0=0,      y1=c_lo,    fillcolor="rgba(30,144,255,0.25)",  line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_lo,   y1=c_imin,  fillcolor="rgba(255,165,0,0.25)",   line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imin, y1=c_imax,  fillcolor="rgba(0,200,81,0.30)",    line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_imax, y1=c_wmax,  fillcolor="rgba(255,165,0,0.25)",   line_width=0, row=1, col=1)
    fig.add_hrect(y0=c_wmax, y1=vpd_max, fillcolor="rgba(255,75,75,0.30)",   line_width=0, row=1, col=1)

    for y_val, label, col in [
        (c_imin, f"Min lý tưởng ({c_imin})", "green"),
        (c_imax, f"Max lý tưởng ({c_imax})", "orange")
    ]:
        fig.add_hline(y=y_val, line_dash="dot", line_color=col,
                      annotation_text=label, annotation_position="top right", row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['temp'].round(1),
        name="Nhiệt độ (°C)", line=dict(color='#E53935', width=2),
        mode='lines+markers', marker=dict(size=4)
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df_chart[x_col], y=df_chart['humi'].round(1),
        name="Độ ẩm (%)", line=dict(color='#1E88E5', width=2),
        mode='lines+markers', marker=dict(size=4)
    ), row=2, col=1)

    fig.update_xaxes(title_text=x_label, row=2, col=1)
    fig.update_layout(
        height=540, template="plotly_white", hovermode='x unified',
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# =========================================================
# --- HÀM HIỂN THỊ METRIC CARD ---
# =========================================================
def show_metrics(last, status, advice, color, u_mail, u_pass, t_mail,
                 selected_crop, key_suffix="default", df_history=None, source=""):
    st.subheader("📍 Thông số mới nhất")
    m1, m2, m3 = st.columns([1, 1.2, 1.8])
    m1.metric("Nhiệt độ", f"{round(last['temp'], 1)} °C")
    m1.metric("Độ ẩm",    f"{round(last['humi'], 1)} %")
    html_box = (
        f'<div style="background-color:{color};padding:15px;border-radius:10px;'
        f'color:white;text-align:center;">'
        f'<h3 style="margin:0;">VPD: {last["VPD"]} kPa</h3><b>{status}</b></div>'
    )
    m2.markdown(html_box, unsafe_allow_html=True)
    m3.warning(f"**Chỉ đạo:** {advice}")
    if "🔴" in status or "🔵" in status:
        if st.button("📧 Gửi Email cảnh báo", key=f"email_btn_{key_suffix}"):
            ok = send_email_alert(
                u_mail, u_pass, t_mail,
                last['VPD'], status, last['temp'], last['humi'],
                selected_crop, df_history, source
            )
            st.success("✅ Đã gửi email chi tiết!") if ok else st.error("❌ Lỗi Gmail — kiểm tra App Password.")

# =========================================================
# --- SIDEBAR ---
# =========================================================
with st.sidebar:
    st.header("📧 Cấu hình Gmail")
    u_mail = st.text_input("Gmail gửi:")
    u_pass = st.text_input("Mật khẩu ứng dụng:", type="password")
    t_mail = st.text_input("Gmail nhận:")
    st.divider()

    st.header("⚙️ Chế độ")
    mode = st.radio("Chọn nguồn dữ liệu:", ["📂 Xem file JSON", "🎲 Mô phỏng Realtime"])
    st.divider()

    selected_crop = st.selectbox("🌱 Loại cây:", list(CROP_VPD.keys()))
    c_info = CROP_VPD[selected_crop]
    st.caption(
        f"Ngưỡng lý tưởng: **{c_info['ideal_min']} – {c_info['ideal_max']} kPa**  \n"
        f"Cảnh báo: > {c_info['warn_max']} kPa"
    )
    st.divider()

    if mode == "📂 Xem file JSON":
        uploaded_file = st.file_uploader("Tải file JSON", type=['json'])

# =========================================================
# --- CHẾ ĐỘ JSON ---
# =========================================================
if mode == "📂 Xem file JSON":
    if uploaded_file:
        df = process_data(uploaded_file)
        if not df.empty:
            df['Tháng'] = df['Thời gian'].dt.strftime('%m/%Y')
            with st.sidebar:
                filter_mode = st.radio("Lọc theo:", ["Tất cả", "Tháng", "Khoảng ngày"])
                if filter_mode == "Tháng":
                    sel_m   = st.multiselect("Chọn tháng:", df['Tháng'].unique(), default=df['Tháng'].unique()[-1:])
                    df_work = df[df['Tháng'].isin(sel_m)].copy()
                elif filter_mode == "Khoảng ngày":
                    date_range = st.date_input(
                        "Kéo chọn khoảng ngày:",
                        value=(df['Thời gian'].min().date(), df['Thời gian'].max().date()),
                        min_value=df['Thời gian'].min().date(),
                        max_value=df['Thời gian'].max().date(),
                    )
                    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                        start = pd.to_datetime(date_range[0])
                        end   = pd.to_datetime(date_range[1]) + timedelta(days=1)
                    else:
                        d     = date_range[0] if isinstance(date_range, (list, tuple)) else date_range
                        start = pd.to_datetime(d)
                        end   = start + timedelta(days=1)
                    df_work = df[(df['Thời gian'] >= start) & (df['Thời gian'] < end)].copy()
                else:
                    df_work = df.copy()

                sel_stt = st.selectbox("📍 Chọn Trạm:", ["Tất cả"] + sorted(df_work['STT'].unique().tolist()))
                if sel_stt != "Tất cả":
                    df_work = df_work[df_work['STT'] == sel_stt]

            df_valid = df_work.dropna(subset=['VPD'])
            if not df_valid.empty:
                last                  = df_valid.iloc[-1]
                status, advice, color = get_greenhouse_advice(last['VPD'], selected_crop)
                show_metrics(last, status, advice, color, u_mail, u_pass, t_mail,
                             selected_crop, key_suffix="file",
                             df_history=df_valid, source=f"JSON / Trạm {sel_stt}")
                st.plotly_chart(draw_chart(df_valid, c_info, smooth=True, x_label="Thời gian"),
                                use_container_width=True)

                st.subheader("📋 Thống kê")
                st.table(df_valid[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))

                def highlight_alert(row):
                    if row['VPD'] > c_info['warn_max']:  return ['background-color:#FFC7CE'] * len(row)
                    if row['VPD'] > c_info['ideal_max']: return ['background-color:#FFE0B2'] * len(row)
                    if row['VPD'] < c_info['low']:       return ['background-color:#D6EAF8'] * len(row)
                    return [''] * len(row)

                styled_df = (
                    df_valid[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
                    .sort_values('Thời gian', ascending=False)
                    .style.apply(highlight_alert, axis=1)
                )
                st.dataframe(styled_df, use_container_width=True)
            else:
                st.error("🚨 Không có dữ liệu hợp lệ.")
        else:
            st.error("🚨 File không hợp lệ hoặc không đọc được dữ liệu.")
    else:
        st.info("👈 Vui lòng tải file JSON ở sidebar.")

# =========================================================
# --- CHẾ ĐỘ REALTIME MÔ PHỎNG ---
# =========================================================
else:
    INTERVAL_SEC = 15  # 15 giây thực = 1 điểm đo (tương đương ~15 phút thực tế)

    if 'rt_history' not in st.session_state:
        st.session_state.rt_history  = pd.DataFrame(columns=['Thời gian', 'temp', 'humi', 'VPD', 'STT'])
        st.session_state.rt_running  = False
        st.session_state.rt_last_gen = None
        st.session_state.rt_sim_time = None

    def init_seed_data():
        t, h      = 28.0, 75.0
        vpd       = calculate_vpd(t, h)
        sim_start = datetime.now().replace(second=0, microsecond=0)
        seed      = pd.DataFrame([{
            'Thời gian': sim_start, 'temp': t, 'humi': h, 'VPD': vpd, 'STT': 'SIM-01'
        }])
        st.session_state.rt_history  = seed
        st.session_state.rt_last_gen = datetime.now()
        st.session_state.rt_sim_time = sim_start

    if st.session_state.rt_history.empty:
        init_seed_data()

    # --- Nút điều khiển ---
    st.subheader("🎛️ Điều khiển mô phỏng")
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])

    with btn_col1:
        if not st.session_state.rt_running:
            if st.button("▶️ Bật", use_container_width=True):
                st.session_state.rt_running  = True
                st.session_state.rt_last_gen = datetime.now()
                if st.session_state.rt_sim_time is None and not st.session_state.rt_history.empty:
                    st.session_state.rt_sim_time = st.session_state.rt_history.iloc[-1]['Thời gian']
                st.rerun()
        else:
            if st.button("⏸️ Tạm dừng", use_container_width=True):
                st.session_state.rt_running = False
                st.rerun()

    with btn_col2:
        if st.button("🔄 Reset dữ liệu", use_container_width=True):
            init_seed_data()
            st.session_state.rt_running = False
            st.success("✅ Đã reset toàn bộ dữ liệu mô phỏng.")
            st.rerun()

    with btn_col3:
        st.metric("📊 Số điểm đo", len(st.session_state.rt_history))

    st.divider()

    # --- Sinh điểm mới nếu đang chạy và đủ interval ---
    if st.session_state.rt_running:
        now     = datetime.now()
        elapsed = (now - (st.session_state.rt_last_gen or now)).total_seconds()

        if elapsed >= INTERVAL_SEC:
            prev       = st.session_state.rt_history.iloc[-1]
            new_temp   = round(np.clip(prev['temp'] + np.random.uniform(-0.8, 0.8), 15, 45), 1)
            new_humi   = round(np.clip(prev['humi'] + np.random.uniform(-3.0, 3.0), 20, 95), 1)
            new_vpd    = calculate_vpd(new_temp, new_humi)
            prev_sim   = st.session_state.rt_sim_time or prev['Thời gian']
            new_sim    = prev_sim + timedelta(minutes=15)
            st.session_state.rt_sim_time = new_sim

            new_row = pd.DataFrame([{
                'Thời gian': new_sim,
                'temp': new_temp, 'humi': new_humi, 'VPD': new_vpd, 'STT': 'SIM-01'
            }])
            st.session_state.rt_history  = pd.concat(
                [st.session_state.rt_history, new_row], ignore_index=True
            ).tail(200)
            st.session_state.rt_last_gen = now

    # --- Trạng thái & đếm ngược ---
    df_rt   = st.session_state.rt_history
    last_rt = df_rt.iloc[-1]
    status_rt, advice_rt, color_rt = get_greenhouse_advice(last_rt['VPD'], selected_crop)

    if st.session_state.rt_running:
        elapsed_now = (datetime.now() - (st.session_state.rt_last_gen or datetime.now())).total_seconds()
        remaining   = max(0, INTERVAL_SEC - int(elapsed_now))
        st.info(f"🟢 Đang chạy — cập nhật tiếp theo sau **{remaining}** giây "
                f"*(mỗi 15 giây = 1 điểm ~ 15 phút thực tế)*")
    else:
        st.warning("⏸️ Mô phỏng đang tạm dừng. Nhấn ▶️ Bật để tiếp tục.")

    # --- Metrics ---
    n_pts = len(df_rt)
    show_metrics(
        last_rt, status_rt, advice_rt, color_rt,
        u_mail, u_pass, t_mail, selected_crop,
        key_suffix=f"rt_{n_pts}", df_history=df_rt, source="Realtime SIM-01"
    )

    # --- Biểu đồ ---
    if len(df_rt) >= 2:
        st.plotly_chart(
            draw_chart(df_rt, c_info, smooth=False,
                       x_label="Thời gian mô phỏng (mỗi điểm ~ 15 phút thực tế)"),
            use_container_width=True
        )
    else:
        st.info("📈 Cần ít nhất 2 điểm để vẽ biểu đồ. Nhấn ▶️ Bật và chờ 15 giây.")

    # --- Thống kê ---
    if len(df_rt) >= 3:
        st.subheader("📋 Thống kê mô phỏng")
        st.table(df_rt[['temp', 'humi', 'VPD']].agg(['max', 'min', 'mean']).round(2))

    # --- Nhật ký ---
    st.subheader("📋 Nhật ký mô phỏng")

    def highlight_rt(row):
        if row['VPD'] > c_info['warn_max']:  return ['background-color:#FFC7CE'] * len(row)
        if row['VPD'] > c_info['ideal_max']: return ['background-color:#FFE0B2'] * len(row)
        if row['VPD'] < c_info['low']:       return ['background-color:#D6EAF8'] * len(row)
        return [''] * len(row)

    styled_rt = (
        df_rt[['Thời gian', 'STT', 'temp', 'humi', 'VPD']]
        .sort_values('Thời gian', ascending=False)
        .style.apply(highlight_rt, axis=1)
    )
    st.dataframe(styled_rt, use_container_width=True)

    # --- Auto-refresh mỗi 5 giây khi đang chạy ---
    if st.session_state.rt_running:
        time.sleep(5)
        st.rerun()
