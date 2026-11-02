import contextlib
import datetime as dt
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/engineering-rails/scripts/rails.py"
spec = importlib.util.spec_from_file_location("rails", SCRIPT)
rails = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rails)

CONTEXT = f"""# Контекст
Актуально на: {dt.date.today()}
## Архитектура
shop/ — stdlib HTTP API.
## Предметная область
Заказы, скидки.
## Бизнес-правила
Деньги округляются до копеек.
## Продакшн
Нет продакшена, только локальный запуск.
## Решения (ADR)
Stdlib only.
## Доступы агента
Только папка проекта.
"""

DESIGN_SMALL = """# Дизайн
## Задача
Экспорт заказов в CSV.
## Решение
Новый эндпоинт в shop/api.py.
## Критерии приёмки
- AC-1: GET /orders/export.csv отдаёт CSV — проверка: test_export
"""

PLAN_SMALL = """# План
## Шаги
- [ ] S1: эндпоинт экспорта — файлы: shop/api.py, tests/test_api.py
"""

VERIFY = """# Проверка
## Автоматические проверки
- `python3 -m unittest` → OK (3 tests)
## Критерии приёмки
- AC-1: PASS — test_export
## Human review
Человек посмотрел формат CSV.
"""

RELEASE = """# Релиз
## Деплой
N/A — продакшена нет, только локальный запуск
## Откат
N/A — продакшена нет, откат через git revert
## Мониторинг ошибок
Ошибки пишутся в stderr сервера.
"""


class RailsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_cmd(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = rails.main(list(args))
        return code, buf.getvalue()

    def task_file(self, name):
        tid = (self.root / ".rails/current").read_text().strip()
        return self.root / ".rails/tasks" / tid / name

    def ready_context(self):
        self.run_cmd("init")
        (self.root / ".rails/context.md").write_text(CONTEXT, encoding="utf-8")

    def start_small(self):
        self.ready_context()
        code, out = self.run_cmd("start", "CSV export", "--lane", "small", "--why", "one endpoint")
        return code, out

    # --- stage 0
    def test_init_template_fails_context_gate(self):
        code, out = self.run_cmd("init")
        self.assertEqual(code, 1)
        self.assertIn("is empty", out)

    def test_start_blocked_without_context(self):
        self.run_cmd("init")
        code, out = self.run_cmd("start", "x", "--lane", "small", "--why", "y")
        self.assertEqual(code, 1)
        self.assertIn("BLOCKED", out)

    def test_stale_context_blocks(self):
        self.run_cmd("init")
        old = CONTEXT.replace(str(dt.date.today()), "2020-01-01")
        (self.root / ".rails/context.md").write_text(old, encoding="utf-8")
        code, out = self.run_cmd("check", "context")
        self.assertEqual(code, 1)
        self.assertIn("days old", out)

    # --- design gate
    def test_design_template_blocks_and_needs_approval(self):
        self.start_small()
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.task_file("01-design.md").write_text(DESIGN_SMALL, encoding="utf-8")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.assertIn("approval", out)
        code, _ = self.run_cmd("approve", "design", "--quote", "да, делаем так")
        self.assertEqual(code, 0)
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)
        self.assertTrue(self.task_file("02-plan.md").exists())

    def test_ac_without_verification_method_rejected(self):
        self.start_small()
        self.task_file("01-design.md").write_text(DESIGN_SMALL.replace(" — проверка: test_export", ""), encoding="utf-8")
        code, out = self.run_cmd("check", "design")
        self.assertEqual(code, 1)
        self.assertIn("проверка", out)

    def test_placeholder_rejected(self):
        self.start_small()
        self.task_file("01-design.md").write_text(DESIGN_SMALL.replace("Экспорт заказов в CSV.", "TODO"), encoding="utf-8")
        code, out = self.run_cmd("check", "design")
        self.assertEqual(code, 1)
        self.assertIn("placeholder", out)

    def test_feature_needs_two_alternatives(self):
        self.ready_context()
        self.run_cmd("start", "promo", "--lane", "feature", "--why", "new domain entity")
        text = "\n".join(f"## {s}\nтекст" for s in rails.DESIGN_SECTIONS["feature"][:-1])
        text = text.replace("## Альтернативы\nтекст", "## Альтернативы\n- только один вариант")
        text += "\n## Критерии приёмки\n- AC-1: скидка применяется — проверка: test_promo\n"
        self.task_file("01-design.md").write_text(text, encoding="utf-8")
        code, out = self.run_cmd("check", "design")
        self.assertEqual(code, 1)
        self.assertIn("at least 2", out)

    def test_hotfix_needs_regression_test_ac(self):
        self.ready_context()
        self.run_cmd("start", "rounding", "--lane", "hotfix", "--why", "one-line bug")
        self.task_file("01-design.md").write_text(
            "## Симптом и ожидаемое поведение\nлишняя копейка\n## Причина\nfloat\n"
            "## Критерии приёмки\n- AC-1: сумма верная — проверка: глазами\n", encoding="utf-8")
        code, out = self.run_cmd("check", "design")
        self.assertEqual(code, 1)
        self.assertIn("regression test", out)

    def go_to_implement(self):
        self.start_small()
        self.task_file("01-design.md").write_text(DESIGN_SMALL, encoding="utf-8")
        self.run_cmd("approve", "design", "--quote", "ок")
        self.run_cmd("advance")
        self.task_file("02-plan.md").write_text(PLAN_SMALL, encoding="utf-8")
        self.run_cmd("approve", "plan", "--quote", "ок")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)

    # --- implement gate / can-edit
    def test_can_edit_denied_before_implement(self):
        self.start_small()
        code, out = self.run_cmd("can-edit", "shop/api.py")
        self.assertEqual(code, 1)
        self.assertIn("code edits only in implement", out)
        code, _ = self.run_cmd("can-edit", ".rails/context.md")
        self.assertEqual(code, 0)

    def test_can_edit_only_plan_files(self):
        self.go_to_implement()
        self.assertEqual(self.run_cmd("can-edit", "shop/api.py")[0], 0)
        code, out = self.run_cmd("can-edit", "shop/pricing.py")
        self.assertEqual(code, 1)
        self.assertIn("not in plan files", out)

    def test_implement_requires_ticked_steps_and_scope(self):
        self.go_to_implement()
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.assertIn("S1", out)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        (self.root / "shop").mkdir()
        (self.root / "shop/pricing.py").write_text("x = 1\n")
        self.task_file("02-plan.md").write_text(PLAN_SMALL.replace("[ ]", "[x]"), encoding="utf-8")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.assertIn("outside the plan: shop/pricing.py", out)
        (self.root / "shop/pricing.py").unlink()
        (self.root / "shop/api.py").write_text("x = 1\n")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)

    # --- verify / release / retro
    def finish_implement(self):
        self.go_to_implement()
        self.task_file("02-plan.md").write_text(PLAN_SMALL.replace("[ ]", "[x]"), encoding="utf-8")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)

    def test_verify_requires_every_ac_pass(self):
        self.finish_implement()
        self.task_file("04-verify.md").write_text(VERIFY.replace("AC-1: PASS", "AC-1: FAIL"), encoding="utf-8")
        code, out = self.run_cmd("check", "verify")
        self.assertEqual(code, 1)
        self.assertIn("AC-1 is not PASS", out)
        self.task_file("04-verify.md").write_text(VERIFY.replace("- AC-1: PASS — test_export\n", "Всё ок\n"), encoding="utf-8")
        code, out = self.run_cmd("check", "verify")
        self.assertIn("AC-1 from the design has no verification line", out)

    def test_ai_task_requires_evals(self):
        self.ready_context()
        self.run_cmd("start", "llm descriptions", "--lane", "feature", "--why", "x", "--ai")
        st = rails.Rails(self.root).load()
        st["stage"] = "verify"
        rails.Rails(self.root).save(st)
        self.task_file("01-design.md").write_text(DESIGN_SMALL, encoding="utf-8")
        self.task_file("04-verify.md").write_text(VERIFY, encoding="utf-8")
        code, out = self.run_cmd("check", "verify")
        self.assertEqual(code, 1)
        self.assertIn("EVALs", out)

    def test_full_flow_to_done_with_metrics(self):
        self.finish_implement()
        self.task_file("04-verify.md").write_text(VERIFY, encoding="utf-8")
        self.run_cmd("approve", "verify", "--quote", "проверил, ок")
        self.assertEqual(self.run_cmd("advance")[0], 0)
        self.task_file("05-release.md").write_text(RELEASE.replace("N/A — продакшена нет, только локальный запуск", "N/A"), encoding="utf-8")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.assertIn("needs a reason", out)
        self.task_file("05-release.md").write_text(RELEASE, encoding="utf-8")
        self.assertEqual(self.run_cmd("advance")[0], 0)
        self.task_file("06-retro.md").write_text("## Узкое место\nревью\n## Что улучшить\nдописать правило\n", encoding="utf-8")
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 1)
        self.assertIn("metrics --write", out)
        code, out = self.run_cmd("metrics", "--write")
        self.assertEqual(code, 0, out)
        self.assertIn("Узкое место по времени", out)
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)
        self.assertEqual(rails.Rails(self.root).load()["stage"], "done")

    # --- back / lane
    def test_back_voids_approvals(self):
        self.go_to_implement()
        code, out = self.run_cmd("back", "design", "--reason", "забыли требование")
        self.assertEqual(code, 1)  # status after back: gate blocked again (approval voided)
        st = rails.Rails(self.root).load()
        self.assertEqual(st["stage"], "design")
        self.assertEqual(st["approvals"], {})
        code, out = self.run_cmd("metrics")
        self.assertIn("Возвратов назад: 1", out)

    def test_lane_downgrade_needs_quote(self):
        self.ready_context()
        self.run_cmd("start", "promo", "--lane", "feature", "--why", "x")
        code, out = self.run_cmd("lane", "small", "--why", "smaller than thought")
        self.assertEqual(code, 1)
        self.assertIn("needs the human", out)
        self.run_cmd("lane", "small", "--why", "smaller", "--quote", "да, это мелочь")
        self.assertEqual(rails.Rails(self.root).load()["lane"], "small")

    def test_combined_approval_small_lane(self):
        self.start_small()
        self.assertTrue(self.task_file("02-plan.md").exists())  # drafted with the design
        self.task_file("01-design.md").write_text(DESIGN_SMALL, encoding="utf-8")
        code, out = self.run_cmd("approve", "design+plan", "--quote", "да")
        self.assertEqual(code, 1)  # plan still a template
        self.task_file("02-plan.md").write_text(PLAN_SMALL, encoding="utf-8")
        code, out = self.run_cmd("approve", "design+plan", "--quote", "да")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_cmd("advance")[0], 0)
        code, out = self.run_cmd("advance")
        self.assertEqual(code, 0, out)
        self.assertEqual(rails.Rails(self.root).load()["stage"], "implement")

    def test_combined_approval_refused_for_feature(self):
        self.ready_context()
        self.run_cmd("start", "promo", "--lane", "feature", "--why", "x")
        code, out = self.run_cmd("approve", "design+plan", "--quote", "да")
        self.assertEqual(code, 1)
        self.assertIn("separately", out)

    def test_pressure_quote_is_not_approval(self):
        self.start_small()
        self.task_file("01-design.md").write_text(DESIGN_SMALL, encoding="utf-8")
        self.task_file("02-plan.md").write_text(PLAN_SMALL, encoding="utf-8")
        code, out = self.run_cmd("approve", "design+plan", "--quote", "Блин, нет времени на это, просто пиши код уже!")
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", out)
        code, out = self.run_cmd("approve", "design+plan", "--quote", "ладно, да, делай так")
        self.assertEqual(code, 0, out)

    def test_risk_accepted_needs_human_words(self):
        self.finish_implement()
        risky = VERIFY.replace("- AC-1: PASS — test_export", "- AC-1: RISK-ACCEPTED — тесты не запустились (память хоста)")
        self.task_file("04-verify.md").write_text(risky, encoding="utf-8")
        code, out = self.run_cmd("check", "verify")
        self.assertEqual(code, 1)
        self.assertIn("needs the human's words", out)
        self.task_file("04-verify.md").write_text(risky.replace("хоста)", "хоста) — человек: «ок, принимаю риск»"), encoding="utf-8")
        code, out = self.run_cmd("check", "verify")
        self.assertEqual(code, 0, out)

    def test_ai_requires_feature_lane(self):
        self.ready_context()
        code, out = self.run_cmd("start", "llm", "--lane", "small", "--why", "x", "--ai")
        self.assertEqual(code, 1)
        self.assertIn("feature", out)

    def test_run_only_plan_step_rejected(self):
        self.start_small()
        self.task_file("02-plan.md").write_text(
            PLAN_SMALL + "- [ ] S2: Запустить unittest через защиту хоста — файлы: tests/test_api.py\n", encoding="utf-8")
        code, out = self.run_cmd("check", "plan")
        self.assertEqual(code, 1)
        self.assertIn("run-only step", out)

    def test_status_without_rails(self):
        code, out = self.run_cmd("status")
        self.assertEqual(code, 1)
        self.assertIn("rails.py init", out)


if __name__ == "__main__":
    unittest.main()
