PackSmart / raspil labels - local Windows package

Что внутри:
- Cutting для ФРЦ\*.xml          исходные XML раскроя
- Cutting для ФРЦ\labels\        сюда генерируются папки labels и labelN.emf
- install.bat                    установить Python-зависимости
- sync-once.bat                  один раз сгенерировать/обновить labels
- sync-every-minute.bat          автоматически обновлять labels каждую минуту

Первый запуск на Windows:
1. Установить Python 3.10+ с python.org, если его нет.
   В установщике включить галочку "Add Python to PATH".
2. Открыть install.bat.
3. Открыть sync-once.bat.

Постоянная работа:
1. Класть новые XML в папку "Cutting для ФРЦ".
2. Запустить sync-every-minute.bat и держать окно открытым.
3. Готовые бирки будут здесь:
   Cutting для ФРЦ\labels\<имя детали>\label1.emf, label2.emf, ...

Интернет нужен только для чтения Google Sheets:
- РАСПИЛ: дата и количество
- Details List: место, материал, размеры, кромка, CNC

Если количество не найдено в РАСПИЛ, программа временно ставит количество равным числу labelN из XML.

Если файл labelN.emf уже правильный, он не перезаписывается.
