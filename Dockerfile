FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=7860
CMD ["bash", "-lc", "python -m streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=$PORT"]
