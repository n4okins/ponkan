FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PONKAN_DATA_DIR=/data PONKAN_PORT=8080
COPY server.py /app/server.py
COPY ponkan /app/ponkan
COPY public /app/public
RUN useradd -r -u 10001 ponkan && mkdir -p /data && chown -R ponkan:ponkan /app /data
USER ponkan
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2)" || exit 1
CMD ["python", "/app/server.py"]
