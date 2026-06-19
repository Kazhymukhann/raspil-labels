# Полная автосинхронизация бирок в Drive — настройка (один раз)

После настройки всё работает само: каждые ~15 минут система читает XML-раскрои из
твоей Drive-папки + данные из таблиц и обновляет бирки в папке `labels`. Поменял
«Место»/задачу в таблице → через несколько минут бирки в Drive обновились. Без кликов.

Запускается бесплатно на GitHub (твой компьютер выключать можно).

Нужно один раз выдать «ключ доступа» к твоему Google Drive (OAuth). Шаги:

## A. Google Cloud — создать ключ
1. Открой <https://console.cloud.google.com> (тем же аккаунтом, где лежат папки).
2. Вверху создай проект (любое имя, напр. `raspil-labels`).
3. Слева **APIs & Services → Library** → найди **Google Drive API** → **Enable**.
4. **APIs & Services → OAuth consent screen**: тип **External** → Create.
   - Заполни имя приложения и свой email (обязательные поля), сохраняй «Save and continue» до конца.
   - На шаге **Test users** → **Add users** → добавь свой email. (Так работать будешь только ты — этого достаточно.)
5. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Тип приложения → **Desktop app** → Create.
   - Нажми **Download JSON**, переименуй файл в **`client_secret.json`** и положи в папку
     `Распил/drive-auto/` (рядом с `get_token.py`).

## B. Получить refresh-токен (один раз, на Mac)
```bash
cd "/Users/kazhyreimbayev/Desktop/Распил/drive-auto"
pip3 install google-auth-oauthlib
python3 get_token.py
```
Откроется браузер → выбери аккаунт → «Дополнительно» → «Перейти (небезопасно)» → Разрешить.
В терминале появятся три строки: **GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN**.

## C. Добавить ключ в GitHub
1. Открой <https://github.com/Kazhymukhann/raspil-labels/settings/secrets/actions>.
2. **New repository secret** → создай по очереди три секрета с именами и значениями из шага B:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REFRESH_TOKEN`

## D. Доступ к папкам
Убедись, что у аккаунта (которым авторизовался в B) есть доступ **на редактирование** к:
- папке с XML — `1jdD9S-D80gBKzjGl-WcJ2G0XLwmKk3Mv`;
- папке `labels` — `1TO1PtrQA5TOvpSzS4TNRcglSIUjGbvbR`.

## E. Запуск
- GitHub → вкладка **Actions** → включи workflows (если попросит) → выбери
  **«Синхронизация бирок в Drive»** → **Run workflow** (проверить вручную).
- Дальше запускается сам каждые ~15 минут.

Готово. Теперь бирки в Drive всегда соответствуют таблицам и раскроям.
