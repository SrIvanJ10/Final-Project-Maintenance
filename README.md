# Mnemosyne

Mnemosyne is a Django + Vue application for systematic literature reviews.

This README focuses on three common tasks:

- run the backend independently
- create a Django superuser
- run the frontend

## Project Structure

```text
MyScience/
|-- myscience/              # Django project
|   |-- manage.py
|   |-- api/
|   |-- core/
|   `-- workflow/
|-- frontend/               # Vue + Vite frontend
|-- requirements.txt
|-- docker-compose.yml
`-- .env.example
```

## Quick Start

If you want the shortest path for local development:

Copy-Item .env.example .env

1. Start infrastructure:

```bash
docker compose build
```

2. Run back-end locally:
```bash
docker compose up
```

3. Run back-end locally:

```bash
docker-compose run web sh -c "python manage.py migrate"
docker-compose run web sh -c "python manage.py createsuperuser"
```

3. In another terminal, run the frontend:

Copy-Item .env.example .env

```bash
cd frontend
npm install
npm run dev
```

## Troubleshooting

### `ModuleNotFoundError`

Install dependencies again:

```bash
pip install -r requirements.txt
```
