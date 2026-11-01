# agents.py
import os

for _proxy_key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    if os.environ.get(_proxy_key, "").lower().startswith("socks://"):
        os.environ.pop(_proxy_key, None)

from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama
from state import MultiAgentState
from tools import ALL_TOOLS, apply_tool_calls, safe_path, save_code_block

# qwen2.5-coder умеет вызывать инструменты. granite4.2 для этого не подходит.
llm = ChatOllama(model="qwen2.5-coder:7b", temperature=0.1, num_ctx=8192).bind_tools(
    ALL_TOOLS
)


def _text_history(history) -> list:
    """Только исходная просьба пользователя.

    Если последней репликой остаётся ответ ассистента, модель продолжает его
    и возвращает пустую строку. План и код агент читает из файлов.
    """
    for item in history:
        if item.__class__.__name__ == "HumanMessage":
            text = (
                item.content
                if isinstance(item.content, str)
                else str(item.content or "")
            )
            if text.strip():
                return [item]
    return []


def talk(prompt: str, history, fallback_file: str = "") -> list:
    """Спросить модель и выполнить её вызовы write_file / read_file / execute_python."""
    messages = [SystemMessage(content=prompt)] + _text_history(history)
    response = llm.invoke(messages)
    new_messages = [response, *apply_tool_calls(response)]
    # Поиск в базе не пишет файл. Один дополнительный ответ нужен, чтобы сохранить результат.
    names = {call.get("name") for call in (getattr(response, "tool_calls", None) or [])}
    if names and "write_file" not in names:
        follow = llm.invoke(messages + new_messages)
        new_messages.append(follow)
        new_messages.extend(apply_tool_calls(follow))
    if fallback_file:
        saved = ensure_saved(new_messages, fallback_file)
        if saved:
            new_messages.append(SystemMessage(content=saved))
    return new_messages


def ensure_saved(messages, file_name: str) -> str:
    """Пишет файл роли, если на диске нет нормального содержимого."""
    from pathlib import Path

    from tools import (
        content_field,
        extract_python,
        file_is_valid,
        safe_path,
        tool_calls_from_text,
        write_file,
    )

    target = safe_path(file_name)
    if file_is_valid(target, file_name):
        return ""
    texts = []
    for item in messages:
        content = getattr(item, "content", "") or ""
        if isinstance(content, str):
            texts.append(content)
        for call in getattr(item, "tool_calls", None) or []:
            args = call.get("args") or {}
            if isinstance(args, dict) and args.get("content"):
                texts.append(str(args["content"]))
    if target.exists():
        texts.append(target.read_text(encoding="utf-8"))
    for text in texts:
        for call in tool_calls_from_text(text):
            args = call["args"]
            wanted = str(args.get("file_path", ""))
            if file_name not in wanted and Path(wanted).name != file_name:
                continue
            return write_file.invoke(
                {"file_path": file_name, "content": str(args.get("content", ""))}
            )
    blob = "\n".join(texts)
    if file_name.endswith(".py"):
        code = extract_python(blob) or extract_python(content_field(blob))
        if (
            file_name.startswith("test_")
            and code
            and "assert" not in code
            and "unittest" not in code
        ):
            code = ""
        if code:
            return write_file.invoke({"file_path": file_name, "content": code})
        raw = content_field(blob)
        if raw.strip() and not file_name.startswith("test_"):
            return write_file.invoke(
                {
                    "file_path": file_name,
                    "content": raw if raw.endswith("\n") else raw + "\n",
                }
            )
        if file_name.startswith("test_"):
            from tools import make_test

            generated = make_test()
            if generated:
                return write_file.invoke({"file_path": file_name, "content": generated})
    saved = save_code_block(blob, file_name)
    if saved and file_is_valid(target, file_name):
        return saved
    if file_name == "plan.txt":
        plan = (
            "1. Реализовать функцию в solution.py по задаче пользователя.\n"
            "2. Проверить краевые случаи в test_solution.py.\n"
            "3. Описать функцию и пример вызова в solution.md.\n"
        )
        return write_file.invoke({"file_path": file_name, "content": plan})
    if file_name.endswith(".md"):
        raw = content_field(blob).strip()
        if raw and "def " not in raw and "read_file" not in raw:
            return write_file.invoke({"file_path": file_name, "content": raw + "\n"})
        for text in reversed(texts):
            body = text.strip()
            if not body or "write_file" in body or "read_file" in body:
                continue
            if (
                body.startswith("{")
                or body.startswith("```")
                or body.startswith("def ")
            ):
                continue
            return write_file.invoke({"file_path": file_name, "content": body + "\n"})
        try:
            source = safe_path("solution.py").read_text(encoding="utf-8")
        except OSError:
            source = ""
        if source.strip():
            doc = (
                "# solution.py\n\nФункция из задачи пользователя.\n\n```python\n"
                + source
                + "```\n"
            )
            return write_file.invoke({"file_path": file_name, "content": doc})
    return ""


# --- 1. АРХИТЕКТОР ---
def architect_node(state: MultiAgentState) -> dict:
    prompt = """Ты Lead Architect. Твоя задача:
    1. Проанализировать запрос пользователя
    2. Поискать в кодовой базе похожие реализации через `search_codebase`
    3. Составить план, учитывая существующие паттерны и утилиты
    4. Указать, какие существующие модули можно переиспользовать
    5. Сохранить план в 'plan.txt' через `write_file`
    
    НЕ пиши код сам. Просто опиши, что должен сделать Coder, и какие существующие функции использовать.
    """

    return {
        "messages": talk(prompt, state["messages"], fallback_file="plan.txt"),
        "status": "coding",
        "iteration": state.get("iteration", 0) + 1,
    }


# --- 2. РАЗРАБОТЧИК (CODER) ---
def coder_node(state: MultiAgentState) -> dict:
    try:
        plan = safe_path("plan.txt").read_text(encoding="utf-8")
    except OSError:
        plan = ""
    prompt = f"""Ты Senior Python Developer.
    Задача: {state.get("task", "Не указана")}
    План:
    {plan}
    
    ТВОЙ АЛГОРИТМ:
    1. Если Architect упомянул существующие утилиты или паттерны, найди их через `search_codebase`
    2. Изучи найденные примеры кода
    3. Напиши чистый, рабочий Python-код, переиспользуя существующие функции где возможно
    4. Сохрани код в 'solution.py' через `write_file`
    
    ПРИНЦИПЫ:
    - Переиспользуй существующий код (DRY - Don't Repeat Yourself)
    - Следуй стилю кода из кодовой базы
    - Импортируй утилиты из sample_codebase, если они подходят
    
    НЕ запускай тесты сам, это работа Tester'а.
    """

    recent_messages = list(state["messages"])[-5:]
    return {
        "messages": talk(prompt, recent_messages, fallback_file="solution.py"),
        "status": "testing",
        "iteration": state.get("iteration", 0) + 1,
    }


# --- 3. ТЕСТИРОВЩИК (TESTER) ---
def tester_node(state: MultiAgentState) -> dict:
    prompt = """Ты QA Engineer. 
    1. Прочитай файл 'solution.py' с помощью `read_file`.
    2. Напиши скрипт тестирования (используя assert или unittest) и сохрани его как 'test_solution.py'.
    3. Запусти 'test_solution.py' с помощью инструмента `execute_python`.
    4. Проанализируй результат. 
       - Если Exit code != 0 или есть ошибки: Верни подробный лог ошибки в чат, чтобы Coder мог её исправить.
       - Если всё успешно: Напиши "✅ Тесты пройдены успешно" и передай управление дальше.
    """
    recent_messages = list(state["messages"])[-5:]
    return {
        "messages": talk(prompt, recent_messages, fallback_file="test_solution.py"),
        "status": "evaluating",
        "iteration": state.get("iteration", 0) + 1,
    }


# --- 4. ТЕХНИЧЕСКИЙ ПИСАТЕЛЬ (DOCUMENTER) ---
def documenter_node(state: MultiAgentState) -> dict:
    prompt = """Ты Technical Writer. 
    Код прошел все тесты. 
    1. Прочитай 'solution.py' через `read_file`.
    2. Напиши описание функции, аргументов и пример использования.
    3. Сохрани его через `write_file` как 'solution.md'. Файл README.md не трогай: там инструкция к проекту.
    4. Напиши финальный краткий отчет для пользователя.
    """
    recent_messages = list(state["messages"])[-5:]
    return {
        "messages": talk(prompt, recent_messages, fallback_file="solution.md"),
        "status": "done",
        "iteration": state.get("iteration", 0) + 1,
    }
