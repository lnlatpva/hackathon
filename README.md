# UDT

Веб-приложение для моделирования производственных процессов, расчёта KPI, поиска узких мест и сравнения сценариев. Стек — Python, FastAPI, Pydantic, NetworkX, SQLAlchemy, PostgreSQL 16 и Vue 3.

## Архитектура

`Vue 3 → FastAPI → PostgreSQL` — основной путь запроса. FastAPI принимает данные от Vue, проверяет их через Pydantic и сохраняет через SQLAlchemy. Для расчёта API передаёт производственный граф в `udt-calc`, где NetworkX помогает анализировать связи и узкие места.

В `app/main.py` находятся вход, модели, версии, сценарии и история. `app/db.py` описывает таблицы PostgreSQL, а `app/calc.py` связывает API с расчётным ядром. Модели, версии, сценарии и результаты хранятся в базе.

## Локальный запуск

Работайте из распакованной папки `udt`. Ниже команды для macOS, Windows 11 (PowerShell, x64) и Ubuntu 24.04 (Bash).

### 1. Установка и запуск PostgreSQL

**macOS** с [Homebrew](https://brew.sh/).

```bash
brew install postgresql@16 python@3.12 node@22
brew services start postgresql@16
"$(brew --prefix postgresql@16)/bin/pg_isready" -h 127.0.0.1 -p 5432
"$(brew --prefix postgresql@16)/bin/psql" -d postgres -v ON_ERROR_STOP=1
```

**Windows** с WinGet. При установке PostgreSQL задайте пароль пользователя `postgres` и оставьте порт `5432`. Затем откройте новое окно PowerShell. [Установщик PostgreSQL для Windows](https://www.postgresql.org/download/windows/).

```powershell
winget install --id Python.Python.3.12 --exact
winget install --id OpenJS.NodeJS.22 --exact
winget install --id PostgreSQL.PostgreSQL.16 --exact --interactive
```

```powershell
Get-Service -Name 'postgresql-x64-16'
& "$env:ProgramFiles\PostgreSQL\16\bin\psql.exe" -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1
```

Если служба остановлена, выполните `Start-Service postgresql-x64-16` в PowerShell от имени администратора. При выборе другого пути установки укажите свой путь к `psql.exe`.

**Ubuntu 24.04**. Node.js 22 устанавливается через nvm. [Документация Node.js](https://nodejs.org/en/download).

```bash
sudo apt update
sudo apt install postgresql-16 python3.12 python3.12-venv curl
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.7/install.sh | bash
. "$HOME/.nvm/nvm.sh"
nvm install 22
sudo systemctl start postgresql
pg_isready -h 127.0.0.1 -p 5432
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1
```

**Все системы.** Один раз выполните в `psql`. Команда `\password` запросит пароль дважды. Если роль и база уже есть, используйте существующие реквизиты.

Для генерации пароля базы и отдельного секрета выполните в другом терминале дважды `python3.12 -c 'import secrets; print(secrets.token_urlsafe(48))'`. На Windows используйте `py -3.12` вместо `python3.12`.

```sql
CREATE ROLE udt_min LOGIN;
\password udt_min
CREATE DATABASE udt_min OWNER udt_min;
\q
```

### 2. FastAPI

**macOS и Ubuntu**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -e ./packages/udt-calc
cp .env.example .env
```

**Windows**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ./packages/udt-calc
Copy-Item .env.example .env
```

В `.env` подставьте пароль `udt_min` в `DATABASE_URL` и отдельный случайный `UDT_SECRET_KEY` длиной от 32 символов. Для пароля со спецсимволами в адресе базы примените URL-кодирование. Сохраните файл и запустите API в своём терминале.

```bash
.venv/bin/python -m uvicorn app.main:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --env-file .env --host 127.0.0.1 --port 8000
```

FastAPI создаст таблицы при первом старте. После создания администратора на странице входа установите `UDT_ALLOW_SETUP=false` в `.env`, остановите Uvicorn через `Ctrl+C` и запустите заново.

### 3. Vue

Откройте второе окно терминала в папке `udt`. На macOS добавьте Node.js в PATH командой `export PATH="$(brew --prefix node@22)/bin:$PATH"`. На Ubuntu в новой сессии при необходимости выполните `. "$HOME/.nvm/nvm.sh" && nvm use 22`.

```bash
cd frontend
npm ci
npm run dev
```

На Windows выполните `cd frontend`, `npm.cmd ci` и `npm.cmd run dev`.

Откройте [UDT](http://127.0.0.1:5173/) и [Swagger](http://127.0.0.1:5173/docs). Vite передаёт запросы `/api`, `/docs`, `/openapi.json` и `/health` на Uvicorn. При смене порта API задайте его и для Vite, например `VITE_API_PROXY=http://127.0.0.1:8002 npm run dev`. В PowerShell это `$env:VITE_API_PROXY = 'http://127.0.0.1:8002'; npm.cmd run dev`.

## Проверка и тесты

Откройте ещё один терминал в папке `udt`, пока оба сервера запущены. Используйте тот же Node.js, что и для запуска Vite.

```bash
.venv/bin/python scripts/check_local.py
.venv/bin/python -m pytest tests packages/udt-calc/tests
npm --prefix frontend test
npm --prefix frontend run build
```

```powershell
.\.venv\Scripts\python.exe scripts/check_local.py
.\.venv\Scripts\python.exe -m pytest tests packages/udt-calc/tests
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

При другом порте API передайте проверке `--backend http://127.0.0.1:8002`.

Для проверки сохранности данных после перезапуска выполните `CREATE DATABASE udt_test OWNER udt_min;` в `psql` от имени администратора. Запустите тест с реквизитами этой базы. Он использует отдельную временную схему.

```bash
UDT_TEST_DATABASE_URL='postgresql+psycopg://udt_min:REPLACE_WITH_DATABASE_PASSWORD@127.0.0.1:5432/udt_test' \
  .venv/bin/python -m pytest tests/test_api.py -k postgresql
```

```powershell
$env:UDT_TEST_DATABASE_URL = 'postgresql+psycopg://udt_min:REPLACE_WITH_DATABASE_PASSWORD@127.0.0.1:5432/udt_test'
.\.venv\Scripts\python.exe -m pytest tests/test_api.py -k postgresql
Remove-Item Env:UDT_TEST_DATABASE_URL
```

Для остановки Uvicorn и Vite нажмите `Ctrl+C` в их терминалах. PostgreSQL продолжит работать как системная служба.