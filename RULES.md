# Self-Development Rules — Torvalds Agent

## Обов'язкові правила

1. Усі само-модифікації (зміни до коду/логіки агента) розміщувати **лише** в `./self-development`.
2. **Не модифікувати головний репозиторій напряму** — використовувати self-development клон.
3. Ці правила мають бути **персистентними** — зберігати їх у репозиторії, щоб вони діяли в майбутніх сесіях.

## Робочі правила для задач у реєстрі проєктів

- Дані/Excel-сховища в робочому каталозі проєкту — **не** є частиною self-development; їх можна обробляти напряму, створюючи результати в каталозі проєкту.
- Скрипти аналізу, які запускаються в каталозі проєкту, — допустимі; обмеження на self-development стосується **зміни самого агента/репозиторію агента**.
- Оригінальні вхідні файли не змінювати — результат пишеться окремим файлом.
- Перед зміною ключа/логіки зведення — прогнати аналіз на даних, показати користувачу наслідки (кількість, підсумки, вартість), і лише потім перезбирати файл.
- Після зборки — обов'язкова верифікація: цілісність zip, XML well-formed, збереження підсумків і сумарної вартості, побайтове збереження `styles.xml` / `sharedStrings.xml` / `<cols>` / індексів стилів `s=`.

---

## Project-specific rules — shodan-toolkit

1. **Never modify the main repository directly.** All changes go into the
   `./self-development` clone; the main checkout stays clean until the work
   is reviewed and explicitly merged.
2. **The Shodan CLI is the contract.** Every argument vector the client
   builds must be accepted by the real `shodan` binary. Each subcommand
   declares its own options, and `click` aborts the whole command on an
   unknown option — before any API call happens. Always run
   `python examples/verify_argv.py` after touching `client.py`.
3. **Keep `tests/test_cli_contract.py` green.** It pins the exact option set
   of shodan 1.31.0. If Shodan changes a subcommand's options, update the
   table deliberately rather than letting the code drift.
4. **Read-only means read-only.** `shodan_raw` is registered in the read-only
   category and is exposed to autonomous agents, so it must refuse every
   state-changing subcommand. Extend `MUTATING_SHODAN_SUBCOMMANDS` when a new
   mutating verb appears in the CLI.
5. **No network in unit tests.** Tests use `FakeRunner` and replay canned
   output. Network-dependent checks live in `examples/`.
6. **Before any commit:** `pytest`, `ruff check .`, `mypy src`,
   `python examples/verify_parsers.py` and `python examples/verify_argv.py`
   must all pass.
7. **Never commit or push without explicit user approval.** Show the diff
   first.
