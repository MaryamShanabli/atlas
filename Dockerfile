FROM python:3.12-slim

WORKDIR /app

# System deps: gcc/libpq-dev for psycopg2, libffi-dev/libjpeg-dev/zlib1g-dev
# for reportlab's font and image handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY ./models ./models
COPY ./alembic ./alembic
COPY ./alembic.ini .
COPY ./notebooks ./notebooks

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
