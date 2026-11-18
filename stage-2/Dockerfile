FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8080
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir "webrouter[search,extract,research]>=0.12.0"
COPY *.py /app/
EXPOSE 8080
CMD ["python", "server.py"]
