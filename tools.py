import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


@tool
def execute_python(code: str, timeout: int = 10) -> str:
    """
    Выполняет python код и возвращает результат

    Returns:
        строка с результатом выполнения (stduot +stderr + exit code)
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_file = f.name
    try:
        result = subprocess.run(
            ["python", temp_file], capture_output=True, text=True, timeout=timeout
        )

        #=====================================
        stdout = (result.stdout or "").rstrip()
        stderr = (result.stderr or "").rstrip()
        lines = []
        if stdout:
            lines.append(stdout)
        if stderr:
            lines.append(stderr)
        lines.append(f"код возврата: {result.returncode}")
        return "\n".join(lines)
        #=====================================

    except subprocess.TimeoutExpired:
        return f"ERROR: Код не завершился за {timeout} секунд (таймаут)"
    except Exception as e:
        return f"ERROR: {str(e)}"
    finally:
        # Удаляем временный файл
        Path(temp_file).unlink(missing_ok=True)


ALL_TOOLS = [execute_python]
