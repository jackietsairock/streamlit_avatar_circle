import io, zipfile, os
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from rembg import remove
import streamlit as st

# --- 全域設定 ---
TARGET_W, TARGET_H = 689, 688
DIAM = min(TARGET_W, TARGET_H)
MARGIN = int(DIAM * 0.08)  # 圓內上、下、左右保留邊距
HEAD_TO_CHEST_RATIO = 0.35 # 估計「頭頂→胸口」約佔人物高度 35%

st.set_page_config(page_title="批次 人像去背 → 圓形頭像 (689x688)", page_icon="🎯", layout="wide")

# --------- 小工具 ---------
def hex_to_rgba(s: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    s = s.lstrip("#")
    if len(s) == 3:  # #abc
        r, g, b = [int(c*2, 16) for c in s]
    else:            # #aabbcc
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    return (r, g, b, alpha)

@st.cache_data(show_spinner=False)
def cutout_rgba(image_bytes: bytes) -> bytes:
    """去背結果以 PNG bytes 回傳（cache 以避免重算）。"""
    im = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    out = remove(im)  # rembg 可吃 PIL Image，回傳 PIL Image
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()

def nonzero_bbox(alpha_img: Image.Image):
    a = np.array(alpha_img)
    ys, xs = np.where(a > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

def enhance_if_small(im: Image.Image) -> Image.Image:
    """若主體偏小/不清晰，做輕量上採樣 + 銳化。（CPU 友善）"""
    w, h = im.size
    # 依最短邊估計，過小則放大 1.3~2.0 倍
    short = min(w, h)
    if short < 450:
        scale = min(2.0, max(1.3, 450 / max(short, 1)))
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    # 輕量銳化
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=3))
    return im

def make_circle_layers(bg_hex: str):
    """建立顏色圓形圖層與圓形遮罩。圓外透明。"""
    bg = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    mask = Image.new("L", (TARGET_W, TARGET_H), 0)
    draw = ImageDraw.Draw(mask)
    left = (TARGET_W - DIAM) // 2
    top  = (TARGET_H - DIAM) // 2
    draw.ellipse([left, top, left + DIAM, top + DIAM], fill=255)
    color_layer = Image.new("RGBA", (TARGET_W, TARGET_H), hex_to_rgba(bg_hex, 255))
    # 將顏色限制在圓形之內
    colored_circle = Image.composite(color_layer, bg, mask)
    return colored_circle, mask

def place_person_in_circle(cutout: Image.Image, bg_hex: str) -> Image.Image:
    """
    cutout: RGBA（透明代表背景）
    依估計比例，讓畫面呈現「頭頂→胸口」位於圓內主要區域，輸出 689x688 的 RGBA，圓外透明。
    """
    # 取得主體 bbox
    bbox = nonzero_bbox(cutout.split()[-1])
    if bbox is None:
        # 完全透明，回傳純圓底
        colored_circle, _ = make_circle_layers(bg_hex)
        return colored_circle

    subject = cutout.crop(bbox)
    subject = enhance_if_small(subject)

    sh = subject.height
    head_to_chest_px = max(1, HEAD_TO_CHEST_RATIO * sh)
    target_span = int(0.62 * DIAM)  # 圓內欲呈現「頭→胸」的像素高度
    scale = target_span / head_to_chest_px

    # 限制不要超出圓形（保留邊界）
    max_w = DIAM - 2 * MARGIN
    max_h = DIAM - 2 * MARGIN
    new_w = int(subject.width * scale)
    new_h = int(subject.height * scale)
    if new_w > 0 and new_h > 0:
        clamp = min(max_w / new_w, max_h / new_h, 2.0)
        scale *= clamp
    subject = subject.resize((int(subject.width * scale), int(subject.height * scale)), Image.LANCZOS)

    # 放置位置：水平置中；垂直讓「頭頂」距離圓頂端留 MARGIN
    out = Image.new("RGBA", (TARGET_W, TARGET_H), (0, 0, 0, 0))
    colored_circle, circle_mask = make_circle_layers(bg_hex)
    out.alpha_composite(colored_circle, (0, 0))

    cx = TARGET_W // 2
    cy = TARGET_H // 2
    circle_top = cy - DIAM // 2

    paste_x = cx - subject.width // 2
    paste_y = circle_top + MARGIN  # 讓主體最上緣靠近圓頂邊距

    out.alpha_composite(subject, (paste_x, paste_y))

    # 圓外透明（套用圓形遮罩到 Alpha）
    final_alpha = ImageChops.multiply(out.split()[-1], circle_mask)
    out.putalpha(final_alpha)
    return out

def process_one(image_bytes: bytes, bg_hex: str) -> Image.Image:
    """整個流程：去背 → 置入圓 → 尺寸校正 → 圖像輸出"""
    cut_png = cutout_rgba(image_bytes)
    cut_img = Image.open(io.BytesIO(cut_png)).convert("RGBA")

    # 先縮放到較接近目標，避免極端大圖耗時
    if max(cut_img.size) > 2200:
        ratio = 2200 / max(cut_img.size)
        cut_img = cut_img.resize((int(cut_img.width * ratio), int(cut_img.height * ratio)), Image.LANCZOS)

    composed = place_person_in_circle(cut_img, bg_hex)
    # 安全保證尺寸
    composed = composed.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    return composed

# --------- 介面 ---------
st.title("🎯 批次人物去背 → 圓形頭像（689×688）")
st.caption("拖曳多張圖片 → 個別選背景色 → 一鍵輸出 ZIP。去背：rembg（ONNXRuntime）；清晰化：輕量上采樣＋銳化。")

uploaded = st.file_uploader(
    "拖曳上傳多張照片（JPG/PNG/WebP）",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True
)

if uploaded:
    st.divider()
    colL, colR = st.columns([1, 1])
    with colL:
        st.subheader("批次設定")
        default_color = st.color_picker("預設背景色", "#F6F6F6")
        export_name = st.text_input("輸出 ZIP 檔名", "avatars.zip")

    st.subheader("每張圖設定與預覽")
    results = []

    for idx, f in enumerate(uploaded):
        st.write("---")
        c1, c2 = st.columns([0.35, 0.65])
        with c1:
            st.write(f"**{f.name}**")
            key = f"color_{idx}_{f.name}"
            color = st.color_picker("背景色", st.session_state.get(key, default_color), key=key)
            st.caption("可與上方預設不同，逐張調整。")
        with c2:
            with st.spinner("去背/生成中…"):
                try:
                    img = process_one(f.getvalue(), color)
                except Exception as e:
                    st.error(f"處理失敗：{e}")
                    continue
            st.image(img, caption="預覽（PNG，圓外透明）", use_column_width=True)
            results.append((os.path.splitext(f.name)[0], img))

    st.write("---")
    if results:
        # 產生 ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for base, im in results:
                out_name = f"{base}.png"  # 保留透明
                b = io.BytesIO()
                im.save(b, format="PNG")
                zf.writestr(out_name, b.getvalue())
        zip_buf.seek(0)
        st.download_button(
            "⬇️ 下載所有已生成的頭像（ZIP）",
            data=zip_buf,
            file_name=export_name or "avatars.zip",
            mime="application/zip",
            use_container_width=True
        )

else:
    st.info("上傳圖片後，這裡會出現每張圖的色盤與預覽。")
