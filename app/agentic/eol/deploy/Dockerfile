FROM mcr.microsoft.com/azure-functions/python:4-python3.11
# Using Azure Functions base for easy App Service compatibility; alternatively use plain python base

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
