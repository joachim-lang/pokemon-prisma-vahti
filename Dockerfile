FROM python:3.12-slim
WORKDIR /app
COPY scraper.py .
ENV FAST_CHECK_SECONDS=8
CMD ["python", "scraper.py", "--fast"]
