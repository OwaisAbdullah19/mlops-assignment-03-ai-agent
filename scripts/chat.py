"""Open the interactive assignment agent with the private prepared configuration."""

import os

from scripts.local_services import environment


def main():
    os.environ.update(environment())
    from agent.main import main as chat

    chat()


if __name__ == "__main__":
    main()
