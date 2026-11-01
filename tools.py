# tools.py
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

for _proxy_key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    if os.environ.get(_proxy_key, "").lower().startswith("socks://"):
        os.environ.pop(_proxy_key, None)

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

ROOT = Path(__file__).resolve().parent
SOLUTION = ROOT / "solution"


@tool
def write_file(file_path: str, content: str) -> str:
    """
    Сохраняет текст в файл. Для сохранения написанного кода или документации.

    Args:
        file_path: Имя файла (например, 'solution.py' или 'README.md')
        content: Содержимое файла
    """
    try:
        path = safe_path(file_path)
        if path.suffix == ".py":
            ast.parse(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f" Файл '{path.name}' успешно сохранен."
    except Exception as e:
        return f" Ошибка записи файла: {e}"


@tool
def read_file(file_path: str) -> str:
    """
    Читает содержимое файла. Для проверки, что написал другой агент.
    """
    try:
        return safe_path(file_path).read_text(encoding="utf-8")
    except Exception as e:
        return f" Ошибка чтения файла: {e}"


@tool
def execute_python(code: str, timeout: int = 10) -> str:
    """
    Выполняет Python-код и возвращает результат (stdout/stderr).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        SOLUTION.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SOLUTION,
        )
        output = []
        if result.stdout:
            output.append(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            output.append(f"STDERR:\n{result.stderr}")
        output.append(f"Exit code: {result.returncode}")
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"ERROR: Таймаут ({timeout} сек)"
    except Exception as e:
        return f"ERROR: {str(e)}"
    finally:
        os.unlink(temp_file)


ALL_TOOLS = [write_file, read_file, execute_python]
TOOLS_BY_NAME = {item.name: item for item in ALL_TOOLS}


def safe_path(file_path: str) -> Path:
    """Любое имя файла ложится в папку solution внутри проекта."""
    raw = Path(file_path)
    parts = raw.parts
    if raw.is_absolute():
        parts = (raw.name,)
    if parts and parts[0] == "solution":
        parts = parts[1:]
    relative = Path(*parts) if parts else Path(raw.name)
    path = (SOLUTION / relative).resolve()
    if path != SOLUTION and SOLUTION not in path.parents:
        raise ValueError(f"путь вне папки solution: {file_path}")
    return path


def tool_calls_from_text(text: str) -> list[dict]:
    """Модель часто печатает вызов текстом, а не полем tool_calls."""
    calls = []
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, offset = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + offset
        if not isinstance(value, dict) or value.get("name") not in TOOLS_BY_NAME:
            continue
        args = value.get("arguments", value.get("args", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                continue
        if isinstance(args, dict):
            calls.append(
                {
                    "name": value["name"],
                    "args": args,
                    "id": value.get("id", value["name"]),
                }
            )
    return calls


def invoke_call(call: dict) -> str:
    name = call.get("name")
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f" Неизвестный инструмент: {name}"
    args = call.get("args") or call.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return str(tool.invoke(args))


def apply_tool_calls(message) -> list[ToolMessage]:
    """Выполняет tool_calls из ответа модели. Без этого файлы не пишутся."""
    calls = list(getattr(message, "tool_calls", None) or [])
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        calls.extend(tool_calls_from_text(content))
    results = []
    for call in calls:
        name = call.get("name")
        results.append(
            ToolMessage(content=invoke_call(call), tool_call_id=call.get("id", name))
        )
    return results


def file_is_valid(path: Path, file_name: str) -> bool:
    """В файле лежит содержимое, а не сырой JSON вызова инструмента."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    text = path.read_text(encoding="utf-8")
    if '"name"' in text and "write_file" in text:
        return False
    if file_name.endswith(".py"):
        try:
            ast.parse(text)
        except SyntaxError:
            return False
        if file_name.startswith("test_"):
            return "assert" in text or "unittest" in text
        return "def " in text
    if file_name == "plan.txt":
        return "def " not in text
    if file_name.endswith(".md"):
        stripped = text.strip()
        if (
            "read_file" in stripped
            or "write_file" in stripped
            or "Ошибка чтения" in stripped
            or stripped.startswith("json")
            or stripped.startswith("def ")
        ):
            return False
    return True


def content_field(text: str) -> str:
    """Достаёт content из текстового JSON, даже если вокруг него ```json."""
    key = '"content"'
    pos = text.find(key)
    if pos < 0:
        return ""
    rest = text[pos + len(key) :].lstrip()
    if not rest.startswith(":"):
        return ""
    rest = rest[1:].lstrip()
    if not rest.startswith('"'):
        return ""
    chars = []
    index = 1
    while index < len(rest):
        char = rest[index]
        if char == "\\":
            nxt = rest[index + 1] if index + 1 < len(rest) else ""
            chars.append(
                {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "'": "'"}.get(nxt, nxt)
            )
            index += 2
            continue
        if char == '"':
            break
        chars.append(char)
        index += 1
    return "".join(chars)


def extract_python(text: str) -> str:
    """Берёт функцию из ответа, даже если вокруг неё обычный текст."""
    if not text:
        return ""
    fenced = _fenced(text)
    if fenced:
        parsed = _parse_python(fenced)
        if parsed:
            return parsed
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "import ", "from ")):
            start = index
            break
    if start is None:
        return ""
    return _parse_python("\n".join(lines[start:]))


def _fenced(text: str) -> str:
    marker = "```"
    start = text.find(marker)
    if start < 0:
        return ""
    body = text[start + len(marker) :]
    if body.startswith("python"):
        body = body[len("python") :]
    end = body.find(marker)
    if end < 0:
        body = body
    else:
        body = body[:end]
    return body.strip()


def _parse_python(code: str) -> str:
    lines = [line for line in code.splitlines() if not line.strip().startswith("```")]
    while lines:
        candidate = "\n".join(lines).strip()
        if not candidate:
            break
        try:
            ast.parse(candidate + "\n")
        except SyntaxError:
            lines.pop()
            continue
        if "def " in candidate:
            return candidate + "\n"
        lines.pop()
    return ""


def make_test() -> str:
    """Собирает unittest по фактическому поведению solution.py."""
    path = safe_path("solution.py")
    if not path.exists():
        return ""
    namespace: dict = {}
    try:
        exec(path.read_text(encoding="utf-8"), namespace)
    except (SyntaxError, NameError):
        return ""
    functions = [
        value
        for key, value in namespace.items()
        if callable(value) and not key.startswith("_")
    ]
    if not functions:
        return ""
    fn = functions[0]
    name = fn.__name__
    methods = []
    for label, arg in (("negative", -1), ("zero", 0), ("one", 1), ("five", 5)):
        try:
            result = fn(arg)
        except ValueError:
            body = (
                f"    def test_{label}(self):\n"
                f"        with self.assertRaises(ValueError):\n"
                f"            {name}({arg})\n"
            )
        else:
            body = (
                f"    def test_{label}(self):\n"
                f"        self.assertEqual({name}({arg}), {result!r})\n"
            )
        methods.append(body)
    return (
        "import unittest\n"
        f"from solution import {name}\n\n"
        "class TestSolution(unittest.TestCase):\n"
        + "\n".join(methods)
        + "\nif __name__ == '__main__':\n"
        "    unittest.main()\n"
    )


def save_code_block(text: str, file_name: str) -> str:
    """Если модель прислала код в ``` и не вызвала write_file."""
    marker = "```"
    start = text.find(marker)
    if start < 0:
        return ""
    body = text[start + len(marker) :]
    if body.startswith("python"):
        body = body[len("python") :]
    end = body.find(marker)
    if end < 0:
        return ""
    content = body[:end].lstrip("\n")
    if not content.strip():
        return ""
    return write_file.invoke({"file_path": file_name, "content": content})
