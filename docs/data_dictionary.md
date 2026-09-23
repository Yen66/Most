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

## Таблицы задач 10–12

- `work_calendar`: глобальная, 730 дат 2026–2027, `cal_date` UNIQUE,
  `is_working`, `day_type`, `is_shortened`, `source`. Неизменяемые строки.
- `acceptance_acts`: tenant; `contract_id` указывает на версию договора,
  `act_number`, `amount_gross NUMERIC(18,2)`, `placed_on`,
  `signed_on`, `refusal_on`, `refusal_reason`, `via_eis`,
  `status`, `valid_from/to`, `superseded_by`, `replace_reason`.
  Один активный номер в пределах версии договора.
- `payment_obligations`: tenant; `act_id` указывает на версию акта,
  `amount NUMERIC(18,2)`, `due_on`, `term_workdays`, `term_basis`,
  `paid_on`, `paid_amount` и четыре поля версионирования.
- `contracts.penalty_cap_pct NUMERIC(9,6)`: nullable; NULL — без договорного
  потолка, явное предупреждение. Значение берётся из активной версии договора.
- `penalty_accruals` отсутствует: пени вычисляются при формировании отчёта.

## cash_flows (миграция 0005)

Tenant-таблица: `id UUID PK`, `company_id UUID FK NOT NULL INDEX`, `contract_id UUID FK NULL`, `object_id UUID FK NULL`, `flow_date DATE NOT NULL`, `direction TEXT inflow|outflow`, `amount NUMERIC(18,2) > 0`, `category TEXT`, `plan_or_fact TEXT plan|fact`, `source_kind TEXT NULL`, `source_id UUID NULL`, `note TEXT NULL`, `valid_from DATE NOT NULL`, `valid_to DATE NULL`, `superseded_by UUID FK NULL`, `replace_reason TEXT NULL`. Именованные CHECK: `ck_cash_flow_direction`, `ck_cash_flow_amount_positive`, `ck_cash_flow_plan_fact`, `ck_cash_flow_source_pair`. Частичный уникальный индекс `uq_cash_flow_source_current(company_id,source_kind,source_id)` для активных автопотоков в SQLite и PostgreSQL. Ручные потоки допускают дубли. Provenance ручных сумм: `value_sources` и `value_refs`; автопоток дополнительно ссылается на версию `payment_obligations`. PostgreSQL immutable trigger, исправление через supersede.


## Артефакт intake (новых таблиц нет)

JSON-квитанция — внешний артефакт, не новая таблица: files[] с полями file, sha256, type, action (imported|skipped|rejected), positions, total_gross, objects[], warnings[], errors[]; summary содержит imported, skipped, rejected, portfolio_gross, portfolio_net. Provenance сохраняется существующими импортёрами в documents, value_sources, value_refs. Повторный sha256 — успешный skipped; неизвестные форматы — rejected.
