### Stage 1 — build: install deps with compiler available
FROM python:3.11-alpine AS builder

RUN apk add --no-cache gcc musl-dev libffi-dev openssh-client

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

### Stage 2 — runtime: lean image with no build tools
FROM python:3.11-alpine

RUN apk add --no-cache openssh-client tzdata

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Application code
COPY *.py ./
COPY templates/ templates/

VOLUME ["/data"]

ENV CHILICON_USERNAME=""
ENV CHILICON_PASSWORD=""
ENV DATA_DIR=/data

EXPOSE 5001

CMD ["python", "enhanced_dashboard.py"]
