from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo


class TimezoneDependencyTests(unittest.TestCase):
    def test_brasilia_iana_timezone_is_available(self) -> None:
        self.assertEqual(str(ZoneInfo("America/Sao_Paulo")), "America/Sao_Paulo")


if __name__ == "__main__":
    unittest.main()
