from __future__ import annotations

from pathlib import Path
from tkinter import Tk

from app import App


def main() -> None:
    app_dir = Path(__file__).resolve().parent
    root = Tk()
    App(root, app_dir / "no_pickup_date_plus_2.json")
    root.mainloop()


if __name__ == "__main__":
    main()
