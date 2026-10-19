# claude-glm-stack (русская версия)

Запуск **Claude Desktop и Claude Code на Z.AI GLM** — с честными,
проверенными тирами моделей и одним API-ключом.

Отдай этот репо своему кодинг-агенту (Claude Code, Codex, Cursor, …) на Mac,
дай ему свой ключ Z.AI — и получишь рабочий Claude Desktop, в котором пикер
моделей пишет GLM и **имеет это в виду**. Единственный возможный ручной шаг —
4 клика в приложении (агент скажет, если они понадобятся).

```text
Claude Desktop (3P gateway mode)
   │  model: claude-opus-5          model: claude-sonnet-4-5
   ▼                                        ▼
локальный реврайт-шлюз  127.0.0.1:8788  (launchd, автозапуск)
   │  model: glm-5.3               model: glm-5.3-flash
   ▼                                        ▼
https://api.z.ai/api/anthropic  (Anthropic Messages API, ключ GLM Coding Plan)
```

## Состав репо

| Путь | Что это |
|---|---|
| `gateway.py` | локальный реврайт-прокси — 3P-эндпоинт приложения Desktop (маппинг тиров выше) |
| `scripts/setup-macos.sh` | установка/удаление гейтвея как launchd-сервиса + конфиг приложения |
| `scripts/selftest.py` | vision-проба: доказывает, какая GLM-модель реально стоит за каждым тиром |
| `scripts/zai-quota.py` | CLI квот GLM Coding Plan: 5-часовое окно, токены день/неделя/месяц, пул MCP |
| `mod/zai-quota-band` | мод Claude Code: рисует эти квоты бандой над промптом |
| `configs/`, `docs/` | примеры конфигов; проверенные факты и аннотированные ссылки на доки |

## Зачем это (две стены)

1. **Claude Desktop не принимает не-Claude имена моделей.** В 3P gateway-режиме
   валидатор режет любой ID с `glm`, `gpt`, `qwen`, … Вписать `glm-5.3` нельзя.
2. **Z.AI принимает `claude-*` имена — и роутит их ВСЕ на GLM-5.3-Flash.**
   Проверено vision-тестом (`docs/findings.md` §2): `claude-opus-5` описывает
   картинки, а настоящий `glm-5.3` — text-only и не видит их. Без транслейтора
   весь твой «GLM-5.3» Desktop молча работает на flash-тире.

Шлюз решает обе: приложение шлёт Claude-образные имена, шлюз переписывает поле
`model` по тирам:

| Тир в Desktop (лейбл) | Шлёт | Реально работает | Как слот в CLI |
|---|---|---|---|
| opus — «GLM-5.3» | `claude-opus-5` | `glm-5.3` (тяжёлый, без vision) | opus-слот |
| sonnet — «GLM-5.3 Flash» | `claude-sonnet-4-5` | `glm-5.3-flash` (быстрый, с vision) | sonnet/haiku |
| haiku | `claude-haiku-*` | `glm-5.3-flash` | haiku-слот |

SSE-стриминг и серверные тула (поиск `web_search_prime` у z.ai) пробрасываются
нетронутыми. Ключ хранится только в `~/.config/claude-glm-stack/key` (600).

## Быстрый старт

**Путь А — отдать репо агенту** (основной):

> «Настрой мне Claude Desktop на GLM по этому репо. Мой ключ Z.AI — …»

Агент идёт по `AGENTS.md`: гоняет `scripts/setup-macos.sh`, перезапускает
приложение, проверяет `scripts/selftest.py` (доказывает: opus-тир слепой =
настоящий `glm-5.3`, sonnet-тир читает картинку = flash, стриминг живёт) и
просит человека сделать 4 клика только если zero-UI маршрут не взялся.

**Путь Б — одной командой:**

```bash
export ZAI_API_KEY="твой-ключ"
./scripts/setup-macos.sh                 # шлюз + managed-конфиг (один раз sudo)
# или без sudo:
./scripts/setup-macos.sh --config-library
```

**Путь В — руками (всегда работает):** подними шлюз (`python3 gateway.py`), в
Claude Desktop: Help → Troubleshooting → Enable Developer Mode → Developer →
Configure Third-Party Inference… → provider `gateway`, endpoint
`http://127.0.0.1:8788`, API key `via-local-gateway` → Apply → Save & Restart.
В claude.ai **не логинься**. Тир-записи возьми из `configs/configlibrary-example.json`.

## Что получаешь

- Полный Claude Desktop (Chat, Cowork, Code) с биллингом на GLM Coding Plan
- Пикер с честными тирами; сабагенты (слот sonnet) — на дешёвом flash
- **Вкладка Code читает твой обычный конфиг Claude Code** — `~/.claude/skills/`,
  плагины, хуки, `~/.claude/CLAUDE.md`, память: миграция не нужна
- Веб-поиск в Chat работает нативно (z.ai реализует серверный `web_search`;
  ест общий пул плана 1000 поисков/мес)
- Все данные локальны (3P-режим хранит чаты на устройстве, аккаунт claude.ai не нужен)
- Банда квот над промптом во вкладке Code — секция ниже

## Банда квот во вкладке Code (`zai-quota-band`)

Мод для Claude Code: рисует расход GLM Coding Plan над промптом:

```
x3 · 5h:12% [09:00-14:00][↻2h05m] · D:1.2m · W:18.4m · M:100.5m · MCP 4/1000
```

- `x1`/`x3` — множитель квоты офпик/пик (пик Z.AI: Пн–Пт 09:00–13:00 МСК)
- `5h:%` — скользящее 5-часовое окно: процент, границы `[старт-конец]`, время до сброса `↻`
- `D/W/M` — токены за сегодня / 7 дней / 30 дней (`k`/`m`/`b`)
- `MCP n/1000` — месячный пул web-search / web-reader / zread

Данные берёт из monitor-API Z.AI (`api.z.ai/api/monitor/usage/...`) через
`scripts/zai-quota.py`: только stdlib, без веб-логина, цепочка ключей как в
`gateway.py` (`$ZAI_API_KEY` → блок `env` в `~/.claude/settings.json` →
`~/.config/claude-glm-stack/key`), кэш на 5 минут в `~/.cache/zai-quota.json`.
API недокументированный (реверс веб-консоли z.ai) и может поменяться.

Включить для всех сессий — добавить в блок `env` файла `~/.claude/settings.json`:

```json
"CLAUDE_CODE_PLUGIN_DIRS": "<путь-к-этому-репо>/mod/zai-quota-band"
```

(или на один запуск: `claude --plugin-dir <путь-к-этому-репо>/mod/zai-quota-band`).
Мод находит скрипт через `$.plugin.root` — работает при любом пути клона.
Банда оборачивает цепочку через `next()` — другие band-моды (например, CTX-метр)
продолжают рисоваться под ней, а не глушатся.

## Проверенные факты (чего нет в других гайдах)

Кратко — подробно в [`docs/findings.md`](docs/findings.md);
все официальные доки (Anthropic 3P + Z.AI) с аннотациями — в
[`docs/links.md`](docs/links.md):

- декодированный из `app.asar` валидатор имён (белый/чёрный списки)
- vision-доказательство: все `claude-*` алиасы у Z.AI → flash
- `/v1/models` у z.ai без `anthropic_family_tier` → нативный discovery не покажет `glm-*`
- карта конфиг-каналов (managed plist / configLibrary / стор приложения / `~/.claude`)
- `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1` — детерминизм без молчаливых подмен
- экономика квот: flash ≈ в 3 раза дешевле; пул поиска 1000/мес общий

## Windows

Репо ориентирован на macOS. Та же архитектура под Windows:
[`kakaballina/claude-desktop-glm-bridge`](https://github.com/kakaballina/claude-desktop-glm-bridge)
(Node-прокси + Task Scheduler). Заметь: ни один из существующих Windows-гайдов
не проверяет, какая модель реально обслуживает тир, — vision-селфтест отсюда
стоит сперевзять.

## Удаление

```bash
./scripts/setup-macos.sh --uninstall
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
