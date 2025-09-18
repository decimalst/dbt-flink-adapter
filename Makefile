COMPOSE ?= docker compose
COMPOSE_DIR ?= envs/flink-1.16

.PHONY: up logs down

up:
cd $(COMPOSE_DIR) && $(COMPOSE) up -d --build

logs:
cd $(COMPOSE_DIR) && $(COMPOSE) logs -f flink-sql-proxy jobmanager

down:
cd $(COMPOSE_DIR) && $(COMPOSE) down -v
