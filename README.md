# Keitaro Studio

Тестовое задание: создание кампании Keitaro и редактирование офферов существующего потока. Сервер написан на FastAPI и SQLAlchemy, интерфейс — HTML/CSS/JavaScript без сборки.

## Что работает

- Создание кампании из названия, ISO-кода страны и ID оффера. Домен, группа и источник выбираются из живых списков Keitaro.
- Первый поток `forced` пропускает указанную страну на `https://www.google.com/`. Второй поток `default` отправляет остальных на оффер с долей 100%.
- Редактор загружает кампании и потоки из Keitaro, позволяет добавлять и удалять офферы, менять доли вручную или выравнивать их. Сохранение требует ровно 100% и защищено от перезаписи изменений, сделанных в Keitaro параллельно.
- SQLAlchemy хранит журнал действий. Данные кампаний и офферов всегда читаются из Keitaro, чтобы цифры в редакторе были актуальными.

## Запуск

Требуется Python 3.9+ и доступ к Keitaro Admin API. API-ключ берётся в панели Keitaro. Пароль от админки приложению не нужен.

```bash
git clone https://github.com/frol1k3/keitaro-studio.git
cd keitaro-studio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Заполните в `.env`:

```dotenv
KEITARO_BASE_URL=https://your-tracker.example
KEITARO_API_KEY=your-admin-api-key
DATABASE_URL=sqlite:///./keitaro_wrapper.db
CAMPAIGN_PREFIX=test_frolov_
```

Затем примените миграции и запустите сервер:

```bash
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Откройте `http://127.0.0.1:8000`. Документация HTTP API доступна по `http://127.0.0.1:8000/docs`.

Для другой БД задайте SQLAlchemy URL в `DATABASE_URL` и снова выполните `alembic upgrade head`. Откат миграции: `alembic downgrade -1` (удалит только локальный журнал действий). `.env` и файл SQLite исключены из Git.

## Проверка

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Тесты используют поддельный Keitaro API без внешних запросов. Они проверяют параметры кампании, порядок и фильтр потоков, изменение долей, конфликт версий и валидацию.

## Устройство API

| Метод | Путь | Действие |
| --- | --- | --- |
| `GET` | `/api/catalog` | Домены, группы, источники и офферы |
| `GET` | `/api/campaigns` | Активные кампании |
| `POST` | `/api/campaigns` | Создать кампанию и два потока |
| `GET` | `/api/campaigns/{id}` | Кампания, потоки и доли офферов |
| `PUT` | `/api/campaigns/{id}/streams/{stream_id}/offers` | Заменить список офферов потока |
| `GET` | `/api/history` | Последние локальные действия |

Клиент Keitaro использует заголовок `Api-Key` и пути `/admin_api/v1`. При изменении офферов передаётся только список `offers` выбранного потока; другие его параметры не меняются. Если создание второго потока не удалось, только что созданная кампания архивируется, чтобы не оставлять активную неполную конфигурацию.

При публикации сервера за пределами локального компьютера поставьте перед ним авторизацию: приложение управляет трекером с серверным API-ключом и рассчитано на запуск оператором, а не на открытый интернет.

Схема API сверена с [официальным справочником Keitaro Admin API](https://admin-api.docs.keitaro.io/) и [описанием типов потоков](https://docs.keitaro.io/en/campaigns-and-streams/streams.html).
