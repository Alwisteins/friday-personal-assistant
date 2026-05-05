@echo off
setlocal
:: Berpindah ke direktori project agar file .env dan instruksi sistem terbaca dengan benar
cd /d "C:\Users\alwiw\Documents\Projects\friday-ai-assistant"
:: Menjalankan main.py menggunakan python
python main.py %*
endlocal
