from .config import Settings
from .store import SeekDBStore


def main() -> None:
    settings = Settings.from_env()
    SeekDBStore(settings).init_schema()
    print(f"NullPath schema ready in {settings.seekdb_database}")


if __name__ == "__main__":
    main()
