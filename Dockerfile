FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY src/ src/

EXPOSE 8777
CMD ["python", "-m", "ragforge.cli", "serve", "--host", "0.0.0.0"]
