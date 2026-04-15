import os
from dotenv import load_dotenv

from src.aris.config.settings import settings

os.chdir(settings.project_root)
load_dotenv(settings.env_path)

from src.aris.app.orchestrator import run_manual_runtime


def main():
    run_manual_runtime()


if __name__ == "__main__":
    main()
