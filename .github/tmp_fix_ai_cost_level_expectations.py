from pathlib import Path

path = Path("tests/test_interactive_console.py")
text = path.read_text(encoding="utf-8")

old = '''            self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (6, 24))
            self.assertEqual((estimate.min_web_calls, estimate.max_web_calls), (4, 8))
            self.assertEqual(estimate.level, "MÉDIO")'''
new = '''            self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (6, 24))
            self.assertEqual((estimate.min_web_calls, estimate.max_web_calls), (4, 8))
            self.assertEqual(estimate.level, "ALTO")'''
if text.count(old) != 1:
    raise RuntimeError("expected exact M18+M20 exposure assertion block")
text = text.replace(old, new, 1)

old = '''        self.assertEqual((estimate.min_pages, estimate.max_pages), (1, 5))
        self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 10))
        self.assertEqual(estimate.level, "BAIXO")'''
new = '''        self.assertEqual((estimate.min_pages, estimate.max_pages), (1, 5))
        self.assertEqual((estimate.min_ai_attempts, estimate.max_ai_attempts), (1, 10))
        self.assertEqual(estimate.level, "MÉDIO")'''
if text.count(old) != 1:
    raise RuntimeError("expected exact URL seed exposure assertion block")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8", newline="\n")
print("Cost risk expectations aligned with retry-aware ceiling")
