一鍵部署到 Streamlit Cloud

把 zip 解壓後整個資料夾上傳到 GitHub（或你現有 repo 裡）。

前往 streamlit.io
 → Sign in → New app。

選擇你的 repo 和 branch，Main file path 填 app.py。

點 Deploy。首次執行會下載去背模型（稍久），之後就快了。

本機開發（可選）
# 建議用虛擬環境
python -m venv .venv && source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt

streamlit run app.py

使用說明（重點）

拖曳多張圖（JPG/PNG/WebP）到上傳區塊

每張圖右側都有色盤可選各自的背景色

確認預覽後，按下「下載 ZIP」取得所有 PNG（圓外透明）

目標尺寸固定 689×688；程式會做去背、構圖、輕量清晰化（上採樣＋銳化）

想加外框線、改預設顏色、或加入上下位移/縮放滑桿微調構圖，跟我說，我幫你再產一版～