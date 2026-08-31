from __future__ import annotations

import ctypes
import json
import os
import re
import string
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    NORMAL,
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Label,
    Listbox,
    PhotoImage,
    Radiobutton,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
)
from tkinter.ttk import Frame, Progressbar
from typing import Any


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SEQUENCE = APP_DIR / "posr_autofill_1_entry.json"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", APP_DIR)) / "POSR Autofill"
IMPORTED_QUEUE_PATH = APP_DATA_DIR / "lead_queue.json"

ONLINE_INQUIRY_TEXT = """Hi {first_name},

This is Fitness First QV Platinum, we just tried calling regarding your online enquiry.

Please give us a call on 8665 4001, reply to this text or text \"OPT OUT\"
We're looking forward to hearing back from you!

Kind regards,
Yuji
Fitness First QV Level 3,
QV Melbourne (next to Daiso) Cnr Russell & Lonsdale Street, Melbourne"""

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_UNICODE = 0x0004
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]


VK_CODES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "cmd": 0x5B,
    "menu": 0x5D,
    "numlock": 0x90,
    "scrolllock": 0x91,
}

for index in range(1, 13):
    VK_CODES[f"f{index}"] = 0x70 + index - 1

for char in string.ascii_lowercase:
    VK_CODES[char] = ord(char.upper())

for digit in string.digits:
    VK_CODES[digit] = ord(digit)

EXTENDED_KEY_CODES = {
    VK_CODES["insert"],
    VK_CODES["delete"],
    VK_CODES["home"],
    VK_CODES["end"],
    VK_CODES["pageup"],
    VK_CODES["pagedown"],
    VK_CODES["left"],
    VK_CODES["right"],
    VK_CODES["up"],
    VK_CODES["down"],
}


@dataclass
class Procedure:
    name: str
    countdown_seconds: int
    default_pause_seconds: float
    queue_mode: str
    variables: list[dict[str, str]]
    steps: list[dict[str, Any]]
    between_leads_steps: list[dict[str, Any]]
    next_lead_steps: list[dict[str, Any]]
    presets: list[dict[str, Any]]
    interface: dict[str, str]


@dataclass
class LeadQueue:
    path: Path
    pending: list[dict[str, str]]
    completed: list[dict[str, Any]]


class KeyboardSender:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._user32.SendInput.argtypes = (ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = ctypes.c_uint
        self._user32.MapVirtualKeyW.argtypes = (ctypes.c_uint, ctypes.c_uint)
        self._user32.MapVirtualKeyW.restype = ctypes.c_uint
        self._user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
        self._user32.OpenClipboard.restype = ctypes.c_bool
        self._user32.EmptyClipboard.argtypes = ()
        self._user32.EmptyClipboard.restype = ctypes.c_bool
        self._user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
        self._user32.SetClipboardData.restype = ctypes.c_void_p
        self._user32.CloseClipboard.argtypes = ()
        self._user32.CloseClipboard.restype = ctypes.c_bool
        self._kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
        self._kernel32.GlobalAlloc.restype = ctypes.c_void_p
        self._kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
        self._kernel32.GlobalLock.restype = ctypes.c_void_p
        self._kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
        self._kernel32.GlobalUnlock.restype = ctypes.c_bool

    def _send_vk(self, vk_code: int, key_up: bool = False) -> None:
        scan_code = self._user32.MapVirtualKeyW(vk_code, 0)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        if vk_code in EXTENDED_KEY_CODES:
            flags |= KEYEVENTF_EXTENDEDKEY
        event = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(ki=KEYBDINPUT(0, scan_code, flags, 0, 0)),
        )
        sent = self._user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(event))
        if sent != 1:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Windows rejected a keyboard input event.")

    def _send_unicode(self, char: str, key_up: bool = False) -> None:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        event = INPUT(
            type=INPUT_KEYBOARD,
            union=INPUT_UNION(ki=KEYBDINPUT(0, ord(char), flags, 0, 0)),
        )
        sent = self._user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(event))
        if sent != 1:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Windows rejected a unicode input event.")

    def press(self, key: str) -> None:
        vk_code = key_to_vk(key)
        self._send_vk(vk_code)
        self._send_vk(vk_code, key_up=True)

    def hotkey(self, keys: list[str]) -> None:
        vk_codes = [key_to_vk(key) for key in keys]
        for vk_code in vk_codes:
            self._send_vk(vk_code)
        for vk_code in reversed(vk_codes):
            self._send_vk(vk_code, key_up=True)

    def text(self, value: str, stop_event: threading.Event) -> None:
        if stop_event.is_set():
            return
        self._paste_text(value)

    def _paste_text(self, value: str) -> None:
        self._set_clipboard_text(value)
        time.sleep(0.05)
        self.hotkey(["ctrl", "v"])

    def copy_text(self, value: str) -> None:
        self._set_clipboard_text(value)

    def _set_clipboard_text(self, value: str) -> None:
        text = value + "\0"
        byte_count = len(text) * ctypes.sizeof(ctypes.c_wchar)
        handle = self._kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_count)
        if not handle:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Could not allocate clipboard memory.")

        locked = self._kernel32.GlobalLock(handle)
        if not locked:
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Could not lock clipboard memory.")

        ctypes.memmove(locked, ctypes.create_unicode_buffer(text), byte_count)
        self._kernel32.GlobalUnlock(handle)

        if not self._user32.OpenClipboard(None):
            error_code = ctypes.get_last_error()
            raise OSError(error_code, "Could not open the clipboard.")
        try:
            if not self._user32.EmptyClipboard():
                error_code = ctypes.get_last_error()
                raise OSError(error_code, "Could not empty the clipboard.")
            if not self._user32.SetClipboardData(CF_UNICODETEXT, handle):
                error_code = ctypes.get_last_error()
                raise OSError(error_code, "Could not set clipboard text.")
            handle = None
        finally:
            self._user32.CloseClipboard()


def key_to_vk(key: str) -> int:
    normalized = key.strip().lower()
    if normalized not in VK_CODES:
        raise ValueError(f"Unsupported key: {key!r}")
    return VK_CODES[normalized]


def load_procedure(path: Path) -> Procedure:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("The procedure file must contain a JSON object.")

    steps = data.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("'steps' must be a list when provided.")

    procedure = Procedure(
        name=str(data.get("name", path.stem)),
        countdown_seconds=int(data.get("countdown_seconds", 5)),
        default_pause_seconds=float(data.get("default_pause_seconds", 0.15)),
        queue_mode=str(data.get("queue_mode", "single")),
        variables=load_variables(data.get("variables", [])),
        steps=steps,
        between_leads_steps=data.get("between_leads_steps", []),
        next_lead_steps=data.get("next_lead_steps", []),
        presets=load_presets(data.get("presets", [])),
        interface=load_interface(data.get("interface", {})),
    )
    validate_steps(procedure.steps)
    if procedure.queue_mode not in {"single", "all_pending"}:
        raise ValueError("'queue_mode' must be 'single' or 'all_pending'.")
    if not isinstance(procedure.between_leads_steps, list):
        raise ValueError("'between_leads_steps' must be a list when provided.")
    if not isinstance(procedure.next_lead_steps, list):
        raise ValueError("'next_lead_steps' must be a list when provided.")
    validate_steps(procedure.between_leads_steps, "between_leads_steps")
    validate_steps(procedure.next_lead_steps, "next_lead_steps")
    if procedure.queue_mode == "all_pending" and not procedure.next_lead_steps:
        raise ValueError("'next_lead_steps' is required when queue_mode is 'all_pending'.")
    if not procedure.steps and not procedure.presets:
        raise ValueError("The procedure must contain a 'steps' list or a 'presets' list.")
    return procedure


def load_interface(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("'interface' must be an object when provided.")
    return {
        "layout": str(value.get("layout", "")).strip(),
        "logo": str(value.get("logo", "")).strip(),
        "posr_procedure": str(value.get("posr_procedure", "")).strip(),
        "posr_description": str(value.get("posr_description", "")).strip(),
    }


def load_presets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("'presets' must be a list when provided.")

    presets: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        label = f"presets[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object.")
        preset_label = str(item.get("label", "")).strip()
        if not preset_label:
            raise ValueError(f"{label}.label is required.")
        preset_steps = item.get("steps")
        if not isinstance(preset_steps, list) or not preset_steps:
            raise ValueError(f"{label}.steps must be a non-empty list.")
        validate_steps(preset_steps, f"{label}.steps")
        presets.append({"label": preset_label, "steps": preset_steps})
    return presets


def load_variables(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("'variables' must be a list when provided.")

    variables: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"variables[{index}] must be an object.")
        name = str(item.get("name", "")).strip()
        if not name:
            raise ValueError(f"variables[{index}].name is required.")
        label = str(item.get("label", name.replace("_", " ").title()))
        variables.append({"name": name, "label": label})
    return variables


def load_lead_queue(path: Path) -> LeadQueue:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return lead_queue_from_data(path, data)


def lead_queue_from_data(path: Path, data: Any) -> LeadQueue:
    if isinstance(data, list):
        pending = data
        completed: list[dict[str, Any]] = []
    elif isinstance(data, dict):
        pending = data.get("pending", data.get("leads", []))
        completed = data.get("completed", [])
    else:
        raise ValueError("Lead queue must be a JSON list or an object with a 'pending' list.")

    if not isinstance(pending, list):
        raise ValueError("'pending' must be a list of leads.")
    if not isinstance(completed, list):
        raise ValueError("'completed' must be a list.")

    return LeadQueue(
        path=path,
        pending=[normalize_lead(lead, index) for index, lead in enumerate(pending, start=1)],
        completed=completed,
    )


def save_lead_queue(queue: LeadQueue) -> None:
    data = {
        "pending": queue.pending,
        "completed": queue.completed,
    }
    with queue.path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def normalize_lead(lead: Any, index: int) -> dict[str, str]:
    if not isinstance(lead, dict):
        raise ValueError(f"Lead {index} must be an object.")

    first_name = read_first_available(lead, "firstname", "first_name", "firstName", "first name")
    last_name = read_first_available(lead, "lastname", "last_name", "lastName", "last name") or "p"
    phone_number = read_first_available(lead, "phone number", "phone_number", "phoneNumber", "phone", "number")

    if not first_name:
        raise ValueError(f"Lead {index} is missing firstname.")
    if not phone_number:
        raise ValueError(f"Lead {index} is missing phone number.")

    return {
        "first_name": str(first_name).strip(),
        "last_name": str(last_name).strip() or "p",
        "phone_number": normalize_phone_number(str(phone_number)),
    }


def read_first_available(data: dict[str, Any], *keys: str) -> str:
    lower_map = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def normalize_phone_number(value: str) -> str:
    cleaned = "".join(char for char in value.strip() if char not in " ()-")
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("0"):
        cleaned = cleaned[1:]
    return "+61" + cleaned


def format_lead(lead: dict[str, Any]) -> str:
    first_name = str(lead.get("first_name", "")).strip()
    last_name = str(lead.get("last_name", "")).strip()
    phone_number = str(lead.get("phone_number", "")).strip()
    return f"{first_name} {last_name} - {phone_number}".strip()


def count_completed_today(completed: list[dict[str, Any]]) -> int:
    today = datetime.now().date().isoformat()
    return sum(1 for lead in completed if str(lead.get("completed_at", "")).startswith(today))


def validate_steps(steps: list[dict[str, Any]], prefix: str = "steps") -> None:
    for index, step in enumerate(steps, start=1):
        label = f"{prefix}[{index}]"
        if not isinstance(step, dict):
            raise ValueError(f"{label} must be an object.")
        step_type = step.get("type")
        if step_type == "press":
            key_to_vk(str(step.get("key", "")))
        elif step_type == "hotkey":
            keys = step.get("keys")
            if not isinstance(keys, list) or not keys:
                raise ValueError(f"{label}.keys must be a non-empty list.")
            for key in keys:
                key_to_vk(str(key))
        elif step_type == "text":
            if "value" not in step:
                raise ValueError(f"{label}.value is required.")
        elif step_type == "wait":
            seconds = float(step.get("seconds", 0))
            if seconds < 0:
                raise ValueError(f"{label}.seconds cannot be negative.")
        elif step_type == "repeat":
            times = int(step.get("times", 0))
            nested = step.get("steps")
            if times < 1:
                raise ValueError(f"{label}.times must be at least 1.")
            if not isinstance(nested, list):
                raise ValueError(f"{label}.steps must be a list.")
            validate_steps(nested, label + ".steps")
        else:
            raise ValueError(f"{label} has unsupported type: {step_type!r}")


def describe_steps(steps: list[dict[str, Any]], indent: int = 0) -> list[str]:
    lines: list[str] = []
    pad = "  " * indent
    for step in steps:
        step_type = step["type"]
        if step_type == "press":
            lines.append(f"{pad}Press {step['key']}")
        elif step_type == "hotkey":
            lines.append(f"{pad}Hotkey {' + '.join(step['keys'])}")
        elif step_type == "text":
            value = str(step["value"])
            preview = value if len(value) <= 48 else value[:45] + "..."
            lines.append(f"{pad}Type {preview!r}")
        elif step_type == "wait":
            lines.append(f"{pad}Wait {step.get('seconds', 0)}s")
        elif step_type == "repeat":
            lines.append(f"{pad}Repeat {step['times']} times")
            lines.extend(describe_steps(step["steps"], indent + 1))
    return lines


def describe_procedure(procedure: Procedure) -> list[str]:
    if procedure.presets:
        lines: list[str] = []
        for preset in procedure.presets:
            lines.append(f"[Preset] {preset['label']}")
            lines.extend(describe_steps(preset["steps"], 1))
        return lines

    if procedure.queue_mode != "all_pending":
        return describe_steps(procedure.steps)

    lines = ["Lead 1 from queue"]
    lines.extend(describe_steps(procedure.steps, 1))
    lines.append("Repeat for each remaining queued lead")
    lines.append("  Gap before next lead")
    lines.extend(describe_steps(procedure.between_leads_steps, 2))
    lines.append("  Next lead from queue")
    lines.extend(describe_steps(procedure.next_lead_steps, 2))
    return lines


def format_date_offset(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%m/%d/%Y")


def render_online_inquiry_text(first_name: str) -> str:
    return ONLINE_INQUIRY_TEXT.format(first_name=first_name.strip())


class App:
    def __init__(self, root: Tk, sequence_path: Path | None = None) -> None:
        self.root = root
        self.root.title("Keystroke Runner")

        self.sender = KeyboardSender()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.sequence_path = sequence_path or DEFAULT_SEQUENCE
        self.procedure = load_procedure(self.sequence_path)
        self.dashboard_mode = self.procedure.interface.get("layout") == "calls_and_posr"
        self.posr_procedure: Procedure | None = None
        if self.dashboard_mode:
            posr_filename = self.procedure.interface.get("posr_procedure")
            if not posr_filename:
                raise ValueError("Dashboard mode requires 'interface.posr_procedure'.")
            self.posr_procedure = load_procedure(self.sequence_path.parent / posr_filename)
        self.root.geometry("780x780" if self.dashboard_mode else "720x520")
        self.variable_values: dict[str, StringVar] = {}
        self.lead_queue: LeadQueue | None = None
        self.current_lead: dict[str, str] | None = None
        self.logo_image: PhotoImage | None = None

        self.status = StringVar(value="Ready")
        self.title = StringVar(value="")
        self.selected_preset = StringVar(value="")
        self.preset_buttons: list[Radiobutton] = []

        frame = Frame(root, padding=12)
        frame.pack(fill=BOTH, expand=True)

        header_frame = Frame(frame)
        header_frame.pack(fill="x", pady=(0, 12))
        logo_filename = self.procedure.interface.get("logo")
        if logo_filename:
            logo_path = self.sequence_path.parent / logo_filename
            self.logo_image = PhotoImage(file=str(logo_path))
            Label(header_frame, image=self.logo_image).pack(side="left", padx=(0, 18))
        header_text = Frame(header_frame)
        header_text.pack(side="left", fill="x", expand=True)
        Label(header_text, textvariable=self.title, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        Label(header_text, textvariable=self.status).pack(anchor="w", pady=(4, 0))

        self.presets_frame = Frame(frame)
        self.presets_frame.pack(fill="x", pady=(0, 10))

        self.variables_frame = Frame(frame)
        self.variables_frame.pack(fill="x", pady=(0, 10))

        button_frame = Frame(frame)
        button_frame.pack(fill="x", pady=(10, 0))

        self.load_button = Button(button_frame, text="Load JSON", command=self.load_json)
        self.dry_button = Button(button_frame, text="Dry Run", command=lambda: self.start(dry_run=True))
        self.run_button = Button(button_frame, text="Run", command=lambda: self.start(dry_run=False))
        self.stop_button = Button(button_frame, text="Stop", state=DISABLED, command=self.stop)

        if not self.dashboard_mode:
            self.load_button.pack(side="left")
            self.dry_button.pack(side="left", padx=6)
            self.run_button.pack(side="left")
        self.stop_button.pack(side="right")

        self.queue_frame = Frame(frame)
        self.queue_frame.pack(fill="x", pady=(12, 8))

        if self.dashboard_mode:
            Label(self.queue_frame, text="B) POSR", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
            posr_description = self.procedure.interface.get("posr_description")
            if posr_description:
                Label(
                    self.queue_frame,
                    text=posr_description,
                    fg="#555555",
                    font=("Segoe UI", 9),
                ).pack(anchor="w", pady=(0, 8))

        queue_controls = Frame(self.queue_frame)
        queue_controls.pack(fill="x", pady=(0, 6))

        self.load_queue_button = Button(queue_controls, text="Load Queue", command=self.load_queue)
        self.load_queue_button.pack(side="left")
        self.posr_run_button: Button | None = None
        if self.dashboard_mode:
            self.posr_run_button = Button(
                queue_controls,
                text="Run POSR",
                command=lambda: self.start_posr(dry_run=False),
                bg="#e4002b",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                padx=18,
            )
            self.posr_run_button.pack(side="left", padx=(8, 0))
        self.import_queue_button = Button(queue_controls, text="Import Pasted Queue", command=self.import_pasted_queue)
        self.import_queue_button.pack(side="left", padx=(6, 0))

        self.import_text = Text(queue_controls, height=4, width=60)
        self.import_text.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.queue_summary = StringVar(value="Queue: none loaded")
        self.today_summary = StringVar(value="POSR today: 0")
        self.queue_status_frame = Frame(self.queue_frame)
        self.queue_status_frame.pack(fill="x", pady=(0, 6))
        Label(self.queue_status_frame, textvariable=self.queue_summary).pack(anchor="w")
        Label(self.queue_status_frame, textvariable=self.today_summary).pack(anchor="w")
        self.queue_progress = Progressbar(self.queue_status_frame, mode="determinate")
        self.queue_progress.pack(fill="x", pady=(4, 0))

        self.queue_list = Listbox(self.queue_frame, height=8)
        self.queue_list.pack(fill="both", expand=True)

        self.messages_frame = Frame(frame)
        if self.dashboard_mode:
            self.messages_frame.pack(fill="x", pady=(8, 8))
            Label(self.messages_frame, text="C) Text Messages", font=("Segoe UI", 12, "bold")).pack(
                anchor="w", pady=(0, 6)
            )
            message_controls = Frame(self.messages_frame)
            message_controls.pack(fill="x")
            Label(message_controls, text="First name:").pack(side="left")
            self.message_first_name = StringVar(value="")
            self.message_first_name_entry = Entry(
                message_controls,
                textvariable=self.message_first_name,
                width=24,
            )
            self.message_first_name_entry.pack(side="left", padx=(8, 8))
            self.copy_online_inquiry_button = Button(
                message_controls,
                text="Text - Online Inquiry",
                command=self.copy_online_inquiry_text,
                bg="#e4002b",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                padx=14,
            )
            self.copy_online_inquiry_button.pack(side="left")
            self.message_first_name_entry.bind("<Return>", lambda _event: self.copy_online_inquiry_text())

        self.step_list = Listbox(frame, height=12)
        self.step_list.pack(fill="both", pady=(4, 0))

        self.refresh_view()

    def refresh_view(self) -> None:
        title = self.procedure.name if self.dashboard_mode else f"{self.procedure.name} - {self.sequence_path.name}"
        self.title.set(title)
        self.refresh_presets()
        self.refresh_variables()
        self.refresh_step_list()

    def refresh_presets(self) -> None:
        for child in self.presets_frame.winfo_children():
            child.destroy()
        self.preset_buttons = []

        if not self.procedure.presets:
            self.selected_preset.set("")
            return

        labels = [preset["label"] for preset in self.procedure.presets]
        if self.selected_preset.get() not in labels:
            self.selected_preset.set(labels[0])

        options_row = self.presets_frame
        if self.dashboard_mode:
            Label(self.presets_frame, text="A) Calls", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 6))
            options_row = Frame(self.presets_frame)
            options_row.pack(fill="x")
        else:
            Label(options_row, text="Option:", width=16, anchor="w").pack(side="left")

        for index, label in enumerate(labels, start=1):
            button = Radiobutton(
                options_row,
                text=f"{index}. {label}" if self.dashboard_mode else label,
                value=label,
                variable=self.selected_preset,
                command=self.refresh_step_list,
            )
            button.pack(side="left", padx=(0, 10))
            self.preset_buttons.append(button)
        self.calls_run_button: Button | None = None
        if self.dashboard_mode:
            self.calls_run_button = Button(
                options_row,
                text="Run Calls",
                command=lambda: self.start_calls(dry_run=False),
                bg="#e4002b",
                fg="white",
                font=("Segoe UI", 10, "bold"),
                padx=18,
            )
            self.calls_run_button.pack(side="right")

    def refresh_step_list(self) -> None:
        self.step_list.delete(0, END)
        for line in describe_steps(self.selected_steps()) if self.procedure.presets else describe_procedure(self.procedure):
            self.step_list.insert(END, line)

    def selected_steps(self) -> list[dict[str, Any]]:
        if not self.procedure.presets:
            return self.procedure.steps
        selected_label = self.selected_preset.get()
        for preset in self.procedure.presets:
            if preset["label"] == selected_label:
                return preset["steps"]
        return self.procedure.presets[0]["steps"]

    def refresh_variables(self) -> None:
        for child in self.variables_frame.winfo_children():
            child.destroy()

        existing_values = {name: value.get() for name, value in self.variable_values.items()}
        self.variable_values = {}

        for variable in self.procedure.variables:
            name = variable["name"]
            row = Frame(self.variables_frame)
            row.pack(fill="x", pady=2)
            Label(row, text=variable["label"], width=16, anchor="w").pack(side="left")
            value = StringVar(value=existing_values.get(name, ""))
            Entry(row, textvariable=value).pack(side="left", fill="x", expand=True)
            self.variable_values[name] = value

    def load_json(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a keystroke procedure",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(APP_DIR),
        )
        if not path:
            return
        try:
            self.sequence_path = Path(path)
            self.procedure = load_procedure(self.sequence_path)
        except Exception as exc:
            messagebox.showerror("Could not load procedure", str(exc))
            return
        self.status.set("Loaded procedure")
        self.refresh_view()

    def load_queue(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose a lead queue",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=str(APP_DIR),
        )
        if not path:
            return
        try:
            self.lead_queue = load_lead_queue(Path(path))
            save_lead_queue(self.lead_queue)
            self.apply_next_lead()
        except Exception as exc:
            messagebox.showerror("Could not load queue", str(exc))
            return
        self.update_queue_status()
        self.refresh_queue_visual()

    def import_pasted_queue(self) -> None:
        raw_json = self.import_text.get("1.0", "end").strip()
        if not raw_json:
            messagebox.showerror("Missing queue JSON", "Paste a queue JSON structure first.")
            return
        try:
            data = json.loads(raw_json)
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            self.lead_queue = lead_queue_from_data(IMPORTED_QUEUE_PATH, data)
            save_lead_queue(self.lead_queue)
            self.apply_next_lead()
        except Exception as exc:
            messagebox.showerror("Could not import queue", str(exc))
            return
        self.status.set(f"Imported queue to {IMPORTED_QUEUE_PATH}")
        self.refresh_queue_visual()

    def apply_next_lead(self) -> None:
        if not self.lead_queue or not self.lead_queue.pending:
            self.current_lead = None
            self.refresh_queue_visual()
            return

        self.current_lead = self.lead_queue.pending[0]
        for name, value in self.current_lead.items():
            if name in self.variable_values:
                self.variable_values[name].set(value)
        self.refresh_queue_visual()

    def complete_current_lead(self) -> None:
        if not self.lead_queue or not self.current_lead or not self.lead_queue.pending:
            return
        completed = self.lead_queue.pending.pop(0)
        completed["completed_at"] = datetime.now().isoformat(timespec="seconds")
        self.lead_queue.completed.append(completed)
        save_lead_queue(self.lead_queue)
        self.current_lead = None

    def update_queue_status(self) -> None:
        if not self.lead_queue:
            return
        self.status.set(
            f"Queue loaded: {len(self.lead_queue.pending)} pending, {len(self.lead_queue.completed)} completed"
        )

    def refresh_queue_visual(self) -> None:
        if not hasattr(self, "queue_progress"):
            return

        self.queue_list.delete(0, END)
        if not self.lead_queue:
            self.queue_summary.set("Queue: none loaded")
            self.today_summary.set("POSR today: 0")
            self.queue_progress.config(maximum=1, value=0)
            return

        pending = len(self.lead_queue.pending)
        completed = len(self.lead_queue.completed)
        total = pending + completed
        today_count = count_completed_today(self.lead_queue.completed)
        self.queue_summary.set(f"Queue: {pending} pending / {completed} completed")
        self.today_summary.set(f"POSR today: {today_count}")
        self.queue_progress.config(maximum=max(total, 1), value=completed)

        for lead in self.lead_queue.pending[:8]:
            self.queue_list.insert(END, "PENDING: " + format_lead(lead))
        if pending > 8:
            self.queue_list.insert(END, f"PENDING: ... {pending - 8} more")
        for lead in self.lead_queue.completed[-4:]:
            self.queue_list.insert(END, "DONE: " + format_lead(lead))

    def start(self, dry_run: bool) -> None:
        self.start_procedure(self.procedure, self.selected_steps(), dry_run, manage_queue=True)

    def start_calls(self, dry_run: bool) -> None:
        self.start_procedure(self.procedure, self.selected_steps(), dry_run, manage_queue=False)

    def start_posr(self, dry_run: bool) -> None:
        if self.posr_procedure is None:
            messagebox.showerror("Missing POSR procedure", "No POSR procedure is configured.")
            return
        self.start_procedure(self.posr_procedure, self.posr_procedure.steps, dry_run, manage_queue=True)

    def copy_online_inquiry_text(self) -> None:
        first_name = self.message_first_name.get().strip()
        if not first_name:
            messagebox.showerror("Missing first name", "Enter the person's first name before copying the text.")
            self.message_first_name_entry.focus_set()
            return
        try:
            self.sender.copy_text(render_online_inquiry_text(first_name))
        except Exception as exc:
            messagebox.showerror("Could not copy text", str(exc))
            return
        self.status.set(f"Text - Online Inquiry copied for {first_name}")

    def start_procedure(
        self,
        procedure: Procedure,
        steps: list[dict[str, Any]],
        dry_run: bool,
        manage_queue: bool,
    ) -> None:
        if self.worker and self.worker.is_alive():
            return
        if procedure.queue_mode == "all_pending":
            if not self.lead_queue or not self.lead_queue.pending:
                messagebox.showerror("Missing queue", "Load or import a queue with at least one pending lead.")
                return
            self.apply_next_lead()
        missing = []
        for variable in procedure.variables:
            name = variable["name"]
            lead_value = self.current_lead.get(name, "") if self.current_lead else ""
            field_value = self.variable_values[name].get() if name in self.variable_values else ""
            if not lead_value and not field_value:
                missing.append(variable["label"])
        if missing:
            messagebox.showerror("Missing values", "Please enter: " + ", ".join(missing))
            return
        self.stop_event.clear()
        self.set_running(True)
        self.worker = threading.Thread(
            target=self.run_procedure,
            args=(procedure, dry_run, steps, manage_queue),
            daemon=True,
        )
        self.worker.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.status.set("Stopping after current step...")

    def set_running(self, running: bool) -> None:
        state = DISABLED if running else NORMAL
        self.load_button.config(state=state)
        self.dry_button.config(state=state)
        self.run_button.config(state=state)
        self.load_queue_button.config(state=state)
        self.import_queue_button.config(state=state)
        if self.calls_run_button is not None:
            self.calls_run_button.config(state=state)
        if self.posr_run_button is not None:
            self.posr_run_button.config(state=state)
        if self.dashboard_mode:
            self.copy_online_inquiry_button.config(state=state)
            self.message_first_name_entry.config(state=state)
        self.stop_button.config(state=NORMAL if running else DISABLED)
        for button in self.preset_buttons:
            button.config(state=state)

    def set_status(self, value: str) -> None:
        self.root.after(0, lambda: self.status.set(value))

    def finish(self, value: str) -> None:
        def update() -> None:
            self.status.set(value)
            self.set_running(False)

        self.root.after(0, update)

    def run_procedure(
        self,
        procedure: Procedure,
        dry_run: bool,
        steps: list[dict[str, Any]],
        manage_queue: bool,
    ) -> None:
        try:
            mode = "dry run" if dry_run else "run"
            for remaining in range(procedure.countdown_seconds, 0, -1):
                if self.stop_event.is_set():
                    self.finish("Stopped before starting")
                    return
                self.set_status(f"Starting {mode} in {remaining}s...")
                time.sleep(1)

            self.execute_steps(steps, dry_run, procedure)
            if self.stop_event.is_set():
                self.finish("Stopped")
            else:
                if procedure.queue_mode == "all_pending":
                    if not dry_run:
                        completed_count = self.complete_queue_run(procedure)
                        self.root.after(0, self.refresh_queue_visual)
                        self.finish(f"Complete. Added {completed_count} referrals.")
                        return
                    self.finish("Dry run complete")
                    return
                if not dry_run and manage_queue:
                    self.complete_current_lead()
                    self.root.after(0, self.apply_next_lead)
                    if self.lead_queue:
                        pending = len(self.lead_queue.pending)
                        completed = len(self.lead_queue.completed)
                        self.root.after(0, self.refresh_queue_visual)
                        self.finish(f"Complete. Queue: {pending} pending, {completed} completed")
                        return
                self.finish("Complete")
        except Exception as exc:
            self.finish("Error")
            self.root.after(0, lambda: messagebox.showerror("Keystroke Runner error", str(exc)))

    def complete_queue_run(self, procedure: Procedure) -> int:
        completed_count = 0
        self.complete_current_lead()
        completed_count += 1

        while self.lead_queue and self.lead_queue.pending and not self.stop_event.is_set():
            self.current_lead = self.lead_queue.pending[0]
            self.root.after(0, self.refresh_queue_visual)
            self.execute_steps(procedure.between_leads_steps, False, procedure)
            if self.stop_event.is_set():
                break
            self.execute_steps(procedure.next_lead_steps, False, procedure)
            if self.stop_event.is_set():
                break
            self.complete_current_lead()
            completed_count += 1

        self.root.after(0, self.apply_next_lead)
        return completed_count

    def execute_steps(
        self,
        steps: list[dict[str, Any]],
        dry_run: bool,
        procedure: Procedure,
    ) -> None:
        for step in steps:
            if self.stop_event.is_set():
                return

            step_type = step["type"]
            self.set_status(self.describe_current_step(step, dry_run))

            if step_type == "press":
                if not dry_run:
                    self.sender.press(str(step["key"]))
            elif step_type == "hotkey":
                if not dry_run:
                    self.sender.hotkey([str(key) for key in step["keys"]])
            elif step_type == "text":
                if not dry_run:
                    self.sender.text(self.render_text(str(step["value"])), self.stop_event)
            elif step_type == "wait":
                self.wait_or_stop(float(step.get("seconds", 0)))
                continue
            elif step_type == "repeat":
                for repeat_index in range(int(step["times"])):
                    if self.stop_event.is_set():
                        return
                    self.set_status(f"Repeat {repeat_index + 1} of {step['times']}")
                    self.execute_steps(step["steps"], dry_run, procedure)

            self.wait_or_stop(procedure.default_pause_seconds)

    def wait_or_stop(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.stop_event.is_set():
                return
            time.sleep(min(0.05, deadline - time.time()))

    @staticmethod
    def describe_current_step(step: dict[str, Any], dry_run: bool) -> str:
        prefix = "Dry run" if dry_run else "Running"
        step_type = step["type"]
        if step_type == "press":
            return f"{prefix}: press {step['key']}"
        if step_type == "hotkey":
            return f"{prefix}: hotkey {' + '.join(step['keys'])}"
        if step_type == "text":
            return f"{prefix}: type text"
        if step_type == "wait":
            return f"{prefix}: wait {step.get('seconds', 0)}s"
        return f"{prefix}: repeat"

    def render_text(self, value: str) -> str:
        rendered = value
        rendered = rendered.replace("{date_plus_2}", format_date_offset(2))
        rendered = rendered.replace("{today_plus_2}", format_date_offset(2))
        if self.current_lead:
            for name, lead_value in self.current_lead.items():
                rendered = rendered.replace("{" + name + "}", str(lead_value))
        for name, variable in self.variable_values.items():
            rendered = rendered.replace("{" + name + "}", variable.get())
        return rendered


def resolve_initial_sequence(argv: list[str]) -> Path:
    if len(argv) < 2:
        return DEFAULT_SEQUENCE

    path = Path(argv[1])
    if not path.is_absolute():
        path = APP_DIR / path
    return path


def main() -> None:
    root = Tk()
    App(root, resolve_initial_sequence(sys.argv))
    root.mainloop()


if __name__ == "__main__":
    main()
