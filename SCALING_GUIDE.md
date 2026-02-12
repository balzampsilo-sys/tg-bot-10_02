# 🚀 Техническое масштабирование

> 📊 **Как масштабировать бот от 10 до 10,000+ пользователей**

---

## 📈 Уровни масштабирования

### 🟢 Level 0: Starter (0-100 пользователей)

**Текущая архитектура:**
```
│
├─ Bot (Docker)
├─ Redis (Docker)
└─ SQLite
```

**Характеристики:**
- 💻 1 CPU, 1GB RAM
- 💾 SQLite (< 100 MB)
- 🔄 < 10 RPS
- ✅ **Работает из коробки!**

**Стоимость:** $5-10/мес (VPS)

---

### 🟡 Level 1: Growing (100-1000 пользователей)

**Миграция на PostgreSQL:**

```bash
# docker-compose.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: booking_bot
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

**Зачем:**
- ✅ Лучшая concurrent performance
- ✅ JSONB для аналитики
- ✅ Full-text search
- ✅ Replication support

**Характеристики:**
- 💻 2 CPU, 4GB RAM
- 💾 PostgreSQL (< 1 GB)
- 🔄 10-50 RPS

**Стоимость:** $20-40/мес

---

### 🟠 Level 2: Business (1000-10,000 пользователей)

**Horizontal Scaling:**

```yaml
# docker-compose.yml
services:
  bot:
    deploy:
      replicas: 3  # 3 экземпляра бота
  
  nginx:
    image: nginx:alpine
    # Load balancer
  
  postgres:
    image: postgres:16-alpine
    # Master-Slave replication
  
  redis:
    image: redis:7-cluster
    # Redis Cluster
```

**Оптимизации:**

1. **Connection Pooling**
```python
# database/connection_pool.py
import asyncpg

pool = await asyncpg.create_pool(
    dsn=DATABASE_URL,
    min_size=10,
    max_size=20,
    command_timeout=60
)
```

2. **Кэширование**
```python
# Кэш списка услуг в Redis
@cached(ttl=300)  # 5 минут
async def get_services():
    return await db.get_active_services()
```

3. **Асинхронные таски**
```python
# Celery для тяжелых операций
from celery import Celery

celery = Celery('booking_bot', broker='redis://redis:6379')

@celery.task
def send_mass_notification(user_ids):
    # Рассылка в фоне
    pass
```

**Характеристики:**
- 💻 4 CPU, 8GB RAM
- 💾 PostgreSQL (< 10 GB)
- 🔄 50-200 RPS

**Стоимость:** $80-150/мес

---

### 🔴 Level 3: Enterprise (10,000+ пользователей)

**Microservices Architecture:**

```
                    ┌────────────────────┐
                    │  Load Balancer    │
                    │   (Nginx/HAProxy) │
                    └────────┬──────────┘
                            │
              ┌─────────┼─────────┐
              │             │            │
          ┌───┴───┐   ┌───┴───┐   ┌───┴───┐
          │ Bot 1  │   │ Bot 2  │   │ Bot 3  │
          └───┬───┘   └───┬───┘   └───┬───┘
              │             │            │
              └─────────┼─────────┘
                        │
         ┌────────────┼────────────┐
         │                           │
    ┌────┴────┐               ┌────┴────┐
    │  Redis   │               │ Postgres │
    │ Cluster │               │ Cluster  │
    └─────────┘               └──────────┘
```

**Компоненты:**

1. **API Gateway**
   - Rate limiting
   - Authentication
   - Request routing

2. **Bot Service** (stateless, horizontal scaling)
   - Несколько экземпляров
   - Auto-scaling
   - Health checks

3. **Background Workers**
   - Celery/RQ для тяжелых задач
   - Отправка напоминаний
   - Аналитика

4. **Database**
   - PostgreSQL Master-Slave
   - Read replicas
   - Connection pooling (PgBouncer)

5. **Cache**
   - Redis Cluster
   - Session storage
   - Rate limiting

6. **Monitoring**
   - Prometheus + Grafana
   - ELK Stack (logs)
   - Uptime monitoring

**Характеристики:**
- 💻 8 CPU, 16GB RAM
- 💾 PostgreSQL (< 100 GB)
- 🔄 200-1000 RPS

**Стоимость:** $300-500/мес

---

## 💾 Миграция на PostgreSQL

### Когда нужно:
- ✅ > 100 активных пользователей
- ✅ > 1000 броней/месяц
- ✅ Нужны concurrent writes
- ✅ Нужна репликация

### План миграции:

```bash
# 1. Создать бэкап SQLite
cp data/bookings.db backups/pre-migration-$(date +%Y%m%d).db

# 2. Экспортировать данные
sqlite3 bookings.db .dump > backup.sql

# 3. Конвертировать в PostgreSQL
pgloader bookings.db postgresql://bot:pass@localhost/booking_bot

# 4. Обновить database/queries.py
# Заменить aiosqlite на asyncpg

# 5. Запустить миграции
python migrate_to_postgres.py
```

---

## 🛡️ Оптимизации производительности

### 1. Database Indexing

```sql
-- Индексы для частых запросов
CREATE INDEX idx_bookings_user_date ON bookings(user_id, booking_date);
CREATE INDEX idx_bookings_date_time ON bookings(booking_date, booking_time);
CREATE INDEX idx_bookings_status ON bookings(status) WHERE status = 'confirmed';
CREATE INDEX idx_services_active ON services(is_active) WHERE is_active = 1;
```

### 2. Query Optimization

```python
# До: N+1 problem
for booking in bookings:
    service = await db.get_service(booking.service_id)  # Много запросов

# После: JOIN
bookings_with_services = await db.get_bookings_with_services()  # 1 запрос
```

### 3. Redis Caching Strategy

```python
# Кэшировать часто используемые данные

# Список услуг (TTL: 5 min)
KEY: "services:active" -> JSON

# Доступные слоты на дату (TTL: 1 min)
KEY: "slots:2026-02-12:service:1" -> JSON

# Статистика пользователя (TTL: 1 hour)
KEY: "stats:user:123456" -> JSON
```

### 4. Webhook Mode

**Вместо long polling:**

```python
# Установить webhook
await bot.set_webhook(
    url="https://your-domain.com/webhook",
    secret_token="your-secret"
)

# FastAPI endpoint
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    update = await request.json()
    await dp.feed_update(bot, Update(**update))
    return {"ok": True}
```

**Преимущества:**
- ⚡ Мгновенный отклик
- 📊 Меньше нагрузка на API
- 🚀 Лучшая масштабируемость

---

## 📊 Мониторинг и Observability

### Metrics (Prometheus + Grafana)

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Метрики
bookings_total = Counter('bookings_total', 'Total bookings')
booking_duration = Histogram('booking_duration_seconds', 'Booking creation time')
active_users = Gauge('active_users', 'Active users')

# Использование
@booking_duration.time()
async def create_booking(...):
    bookings_total.inc()
    # ...
```

### Logging (ELK Stack)

```yaml
# docker-compose.monitoring.yml
services:
  elasticsearch:
    image: elasticsearch:8.11.0
  
  logstash:
    image: logstash:8.11.0
  
  kibana:
    image: kibana:8.11.0
    ports:
      - "5601:5601"
```

### Tracing (Jaeger)

```python
# Распределенное трейсинг
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("create_booking")
async def create_booking(...):
    # Отслеживание всей цепочки
    pass
```

---

## 🔒 Безопасность

### 1. Secrets Management

```bash
# Использовать Vault или AWS Secrets Manager

# docker-compose.yml
services:
  bot:
    environment:
      - BOT_TOKEN=${BOT_TOKEN}  # Из .env
    secrets:
      - db_password
      - redis_password

secrets:
  db_password:
    external: true
  redis_password:
    external: true
```

### 2. Network Security

```yaml
# Изолированные сети
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true  # Нет внешнего доступа
```

### 3. Rate Limiting

```python
# Уже реализовано в middlewares/rate_limit.py
# Для scaling добавьте:

# Redis-based distributed rate limiting
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

class DistributedRateLimiter:
    async def check_rate_limit(self, user_id: int) -> bool:
        key = f"ratelimit:{user_id}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        return count <= 30  # 30 запросов/минуту
```

---

## 🔄 CI/CD Pipeline

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          pip install -r requirements.txt
          pytest tests/
  
  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          ssh user@server 'cd /app && git pull && docker compose up -d --build'
```

### Blue-Green Deployment

```bash
# Без downtime deployment

# 1. Запустить новую версию (green)
docker compose -f docker-compose.green.yml up -d

# 2. Проверить health
curl http://localhost:8081/health

# 3. Переключить load balancer
nginx -s reload

# 4. Остановить старую версию (blue)
docker compose -f docker-compose.blue.yml down
```

---

## 🌐 Multi-region Deployment

### Для глобального бизнеса:

```
Region 1 (EU)          Region 2 (Asia)        Region 3 (US)
┌────────────┐       ┌────────────┐       ┌────────────┐
│ Bot + Redis │ ↔ │ Bot + Redis │ ↔ │ Bot + Redis │
└────┬───────┘       └────┬───────┘       └────┬───────┘
     │                   │                   │
     └───────────────┼───────────────────┘
                       │
              ┌────────┴────────┐
              │ Global Postgres │
              │   (Primary +    │
              │   Read Replicas)│
              └─────────────────┘
```

---

## 💸 Экономика масштабирования

| Уровень | Пользователи | Инфраструктура | Доход/мес | Расходы/мес | Profit |
|---------|------------|--------------|------------|--------------|--------|
| Starter | 10-100 | $10/мес | 0₽ | 10,000₽ | -10,000₽ |
| Growing | 100-1K | $40/мес | 500K₽ | 150,000₽ | 350K₽ |
| Business | 1K-10K | $150/мес | 3.8M₽ | 1,500,000₽ | 2.3M₽ |
| Enterprise | 10K+ | $500+/мес | 15M+₽ | 5,000,000₽ | 10M+₽ |

---

## 🛠️ Инструменты для масштабирования

### Infrastructure as Code

**Terraform:**
```hcl
# infrastructure/terraform/main.tf
resource "aws_instance" "bot" {
  count = 3
  ami = "ami-ubuntu-22.04"
  instance_type = "t3.medium"
  
  tags = {
    Name = "booking-bot-${count.index}"
  }
}
```

**Kubernetes:**
```yaml
# k8s/deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-bot
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: bot
        image: booking-bot:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### Auto-scaling

```yaml
# k8s/hpa.yml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: booking-bot-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: booking-bot
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 📊 Роадмап масштабирования

### Q1 2026 (0-100 users)
- ✅ Docker Compose setup
- ✅ Redis FSM storage
- ✅ Базовое логирование
- ✅ Community support

### Q2 2026 (100-500 users)
- ☐ Миграция на PostgreSQL
- ☐ Connection pooling
- ☐ Кэширование в Redis
- ☐ PRO фичи

### Q3 2026 (500-2000 users)
- ☐ Horizontal scaling (3+ instances)
- ☐ Prometheus + Grafana
- ☐ Webhook mode
- ☐ Background workers (Celery)

### Q4 2026 (2000-10,000 users)
- ☐ Kubernetes deployment
- ☐ Auto-scaling
- ☐ Multi-region
- ☐ CDN для статики

---

## 📝 Чеклист масштабирования

### Перед масштабированием проверьте:

- [ ] Load testing (нагрузочное тестирование)
- [ ] Database indexes (все нужные индексы)
- [ ] Connection pooling (пул соединений)
- [ ] Caching strategy (стратегия кэширования)
- [ ] Monitoring & alerts (мониторинг и алерты)
- [ ] Backup strategy (стратегия бэкапов)
- [ ] Disaster recovery plan (план восстановления)
- [ ] Security audit (аудит безопасности)

---

## 📚 Дополнительные ресурсы

- [BUSINESS_MODEL.md](BUSINESS_MODEL.md) - Бизнес-модель
- [MONITORING_ALTERNATIVES.md](MONITORING_ALTERNATIVES.md) - Альтернативы Sentry
- [CRITICAL_FIXES_COMPLETED.md](CRITICAL_FIXES_COMPLETED.md) - Критичные фиксы

---

**Статус:** 🟢 Ready for Scale  
**Дата:** 12 февраля 2026
