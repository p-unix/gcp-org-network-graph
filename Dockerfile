FROM python:3.9-slim

WORKDIR /app

# Copy application code
COPY requirements.txt app.py nw_pycharm_2.py /app/
COPY template/ /app/template/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN dir
RUN ls

# Expose the Flask port
EXPOSE 5000

# Start the Flask app
CMD ["flask", "run", "--host=0.0.0.0"]
