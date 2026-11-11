import os
import tempfile
import unittest
from pathlib import Path

import run_main


class TestResourcePath(unittest.TestCase):
    def test_resource_path_is_relative_to_launcher_not_working_directory(self):
        launcher_dir = Path(run_main.__file__).resolve().parent
        original_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as other_directory:
            try:
                os.chdir(other_directory)
                resource_path = Path(run_main.get_resource_path("app.py"))
            finally:
                os.chdir(original_directory)

        self.assertEqual(resource_path, launcher_dir / "app.py")


if __name__ == "__main__":
    unittest.main()
