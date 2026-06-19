#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Разовое получение refresh-токена Google Drive (запускается ОДИН раз на твоём Mac).

1) В Google Cloud создай OAuth client (тип «Desktop app») и скачай client_secret.json
   (положи рядом с этим файлом). Включи Google Drive API. См. SYNC_SETUP.md.
2) Запусти:  python3 get_token.py
   Откроется браузер -> выбери аккаунт (у которого есть доступ к папкам) -> Разрешить.
3) Скрипт напечатает CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN — добавь их в GitHub Secrets.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
HERE = os.path.dirname(os.path.abspath(__file__))

flow = InstalledAppFlow.from_client_secrets_file(
    os.path.join(HERE, "client_secret.json"), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")

print("\n================  ДОБАВЬ В GitHub Secrets  ================")
print("GOOGLE_CLIENT_ID     =", creds.client_id)
print("GOOGLE_CLIENT_SECRET =", creds.client_secret)
print("GOOGLE_REFRESH_TOKEN =", creds.refresh_token)
print("===========================================================")
print("(если REFRESH_TOKEN пустой — отзови доступ аккаунту в "
      "myaccount.google.com/permissions и запусти снова)")
