import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.conf import settings
from django.test import SimpleTestCase


@skipUnless(os.name == "posix", "Deployment scripts require POSIX shell")
class DeploymentScriptTests(SimpleTestCase):
    def run_deploy(self, first=False, state="running", volume=True, dump_failure=False):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "deploy" / "scripts"
            scripts.mkdir(parents=True)
            (root / "data" / "media").mkdir(parents=True)
            for filename in ("deploy.sh", "backup.sh"):
                shutil.copyfile(settings.BASE_DIR / "deploy" / "scripts" / filename, scripts / filename)
            (root / ".env.production").write_text("POSTGRES_USER=qa\nPOSTGRES_DB=qa\n", encoding="utf-8")
            binaries = root / "bin"
            binaries.mkdir()
            commands = {
                "git": 'echo "git $*" >> "$QA_LOG"\nexit 0\n',
                "stat": 'echo 10001\n',
                "getfacl": 'echo user:www-data:r-x\n',
                "python3": 'exit 0\n',
                "docker": '''echo "docker $*" >> "$QA_LOG"
case "$*" in
  "inspect --format "*) echo '{}' ;;
  *"ps -a -q db") [ "$QA_STATE" = absent ] || echo qa-db ;;
  *"ps --status running -q db") [ "$QA_STATE" != running ] || echo qa-db ;;
  "volume inspect "*) [ "$QA_VOLUME" = 1 ] ;;
  *"pg_dump "*) [ "$QA_DUMP_FAILURE" != 1 ] || exit 1; echo simulated-dump ;;
  *"pg_restore --list") cat >/dev/null ;;
  *"redis-cli ping") echo PONG ;;
  *"inspect ping"*) echo pong ;;
esac
''',
            }
            for name, body in commands.items():
                executable = binaries / name
                executable.write_text("#!/bin/sh\n" + body, encoding="utf-8")
                executable.chmod(0o755)
            log = root / "calls.log"
            result = subprocess.run(
                ["/bin/sh", str(scripts / "deploy.sh")],
                cwd=root,
                env={
                    **os.environ, "PATH": f"{binaries}:{os.environ['PATH']}",
                    "FIRST_DEPLOY": "1" if first else "0", "QA_LOG": str(log),
                    "QA_STATE": state, "QA_VOLUME": "1" if volume else "0",
                    "QA_DUMP_FAILURE": "1" if dump_failure else "0",
                    "ENV_FILE": ".env.production",
                },
                capture_output=True, text=True, timeout=20, check=False,
            )
            return result, log.read_text() if log.exists() else ""

    def test_first_deploy_rejects_existing_database(self):
        result, calls = self.run_deploy(first=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("git pull", calls)

    def test_update_refuses_stopped_database(self):
        result, calls = self.run_deploy(state="stopped")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("git pull", calls)

    def test_failed_backup_prevents_pull_and_migrations(self):
        result, calls = self.run_deploy(dump_failure=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pg_dump", calls)
        self.assertNotIn("git pull", calls)
        self.assertNotIn("run --rm --no-deps migrate", calls)

    def test_verified_backup_precedes_pull_and_migrations(self):
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index("pg_restore --list"), calls.index("git pull"))
        self.assertLess(calls.index("git pull"), calls.index("run --rm --no-deps migrate"))
