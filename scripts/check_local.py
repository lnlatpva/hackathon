"""Проверяет работающие Uvicorn и Vite без изменения данных."""

from argparse import ArgumentParser

import httpx


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check(backend: str, frontend: str) -> None:
    backend = backend.rstrip('/')
    frontend = frontend.rstrip('/')

    with httpx.Client(timeout=5, trust_env=False) as client:
        health = client.get(f'{backend}/health').raise_for_status().json()
        require(health['status'] == 'ok', 'FastAPI не подтвердил готовность')

        page = client.get(f'{frontend}/models').raise_for_status().text
        require('id="app"' in page, 'Vite не вернул страницу Vue для /models')

        docs = client.get(f'{frontend}/docs').raise_for_status().text
        require('Swagger UI' in docs, 'Vite не вернул Swagger UI для /docs')

        schema = client.get(f'{frontend}/openapi.json').raise_for_status().json()
        require('/api/models' in schema['paths'], 'Vite не вернул схему API')
        require(schema['info']['version'] == health['version'], 'Версии API не совпадают')

        proxied_health = client.get(f'{frontend}/health').raise_for_status().json()
        require(proxied_health == health, 'Ответ /health через Vite отличается от ответа FastAPI')

        models = client.get(f'{frontend}/api/models')
        require(models.status_code == 401, 'Защищённый /api/models должен вернуть 401')
        require(models.json()['detail'] == 'Bearer token required', 'Ответ /api/models получен не от FastAPI')

        # Запрос проверяет чтение из БД через API и не создаёт учётную запись.
        login = client.post(f'{frontend}/api/auth/login', json={
            'login': 'udt-smoke-check', 'password': 'invalid-smoke-check-password',
        })
        require(login.status_code == 401, 'Проверка чтения из БД через /api/auth/login не прошла')
        require(login.json()['detail'] == 'Invalid credentials', 'API не подтвердил проверку входа')


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--backend', default='http://127.0.0.1:8000')
    parser.add_argument('--frontend', default='http://127.0.0.1:5173')
    args = parser.parse_args()

    try:
        check(args.backend, args.frontend)
    except (httpx.HTTPError, KeyError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Проверка запуска не прошла: {exc}\n')
    print('FastAPI, Vue, Swagger, прокси и чтение из БД работают.')


if __name__ == '__main__':
    main()