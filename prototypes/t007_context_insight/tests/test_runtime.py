import unittest

from prototypes.t007_context_insight.runtime import (
    DeviceError,
    run_with_bounded_retry,
    require_xpu,
)


class _UnavailableXpu:
    @staticmethod
    def is_available():
        return False


class _FakeTorchWithoutXpu:
    pass


class _FakeTorchUnavailable:
    xpu = _UnavailableXpu()


class RuntimeGuardTests(unittest.TestCase):
    def test_missing_xpu_api_is_rejected(self):
        with self.assertRaisesRegex(DeviceError, "XPU API"):
            require_xpu(_FakeTorchWithoutXpu())

    def test_unavailable_xpu_is_rejected_without_cpu_fallback(self):
        with self.assertRaisesRegex(DeviceError, "unavailable"):
            require_xpu(_FakeTorchUnavailable())

    def test_retry_is_bounded(self):
        attempts = []

        def always_invalid():
            attempts.append(1)
            return "not-json"

        with self.assertRaisesRegex(RuntimeError, "3 attempts"):
            try:
                run_with_bounded_retry(always_invalid, max_attempts=3)
            except RuntimeError as exc:
                self.assertEqual(exc.attempts, 3)
                raise

        self.assertEqual(len(attempts), 3)


if __name__ == "__main__":
    unittest.main()
