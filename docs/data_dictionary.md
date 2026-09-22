# Словарь данных

Существующие таблицы фундамента сохраняют назначение. Ниже — изменения задач 5–8.

## contracts
Добавлены `signed_on DATE NULL`, `award_reduction_factor NUMERIC(9,6) NULL`, `valid_from DATE NOT NULL`, `valid_to`, `superseded_by`, `replace_reason`. Активная версия: `valid_to IS NULL`. Частичный индекс `uq_contract_current(company_id, number)` задан для PostgreSQL и SQLite. Фактор снижения хранится, но в выручку не применяется.

## objects
Версионируется четырьмя полями периода. Старый непарциальный `UNIQUE(company_id,name)` снят. Активная уникальность — `uq_object_current(company_id,name) WHERE valid_to IS NULL` для обоих диалектов.

## schedule_tasks
Добавлены четыре поля версии. Активная уникальность: `(company_id, object_id, position_no, front) WHERE valid_to IS NULL` с `postgresql_where` и `sqlite_where`.

## cost_articles
Глобальный плоский справочник: `id`, `code UNIQUE`, `category`, `name`, `unit`, `is_active`, `sort_order`. `company_id` отсутствует по ADR-0011. CHECK категории: `direct|indirect|financial|other`.

## cost_entries
Tenant-таблица затрат: связи с объектом/договором/позицией, `article_code` FK, `quantity`, `unit`, `price`, `amount`, `amount_type`, `rate_value`, `vat_mode`, `vat_rate`, `source_id`, поля версии, `created_at`, `created_by`. `amount_net` и `vat_amount` отсутствуют. CHECK гарантирует enum и ровно одну форму суммы: fixed→amount, share_of_revenue→rate_value.

## scenarios
Версионируемый сценарий с `company_id`, `name`, `object_id`, `contract_id`, `base_date`, provenance, автором и полями версии. Активный индекс `(company_id, object_id, name) WHERE valid_to IS NULL` для PostgreSQL и SQLite.

## scenario_params
Immutable-дочерняя таблица без полей версии: `param_type`, `scope`, `scope_value`, `param_value`, автор и время. CHECK контролируют тип параметра, scope, согласованность scope_value и положительное значение.
