import json
import operator
import re
import uuid
from typing import Annotated, TypedDict, Literal, Sequence

from langchain_core import messages
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools.base import _TOOL_CALL_SCHEMA_FIELDS
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from pydantic import InstanceOf

from tools import ALL_TOOLS, tempfile

# ===== Config ============
LLM_MODEL = "qwen2.5-coder:7b"
TEMPERATURE = 0.1
MAX_ITER = 5

# =======================================
# 1. Определение state
# =======================================


class AgentState(TypedDict):
    """
    Состояние агента.

    messages: История диалога (список сообщений)
    iteration: Счетчик итераций (для защиты от зацикливания)
    """

    messages: Annotated[Sequence[BaseMessage], operator.add]


SYSTEM_PROMPT = """Ты — AI-ассистент для написания кода на Python.

Твоя задача:
1. Понять задачу пользователя
2. Написать рабочий код
3. Выполнить код через инструмент execute_python
4. Проверить результат
5. Если есть ошибки — исправить и выполнить снова
6. Когда код работает корректно — дать финальный ответ пользователю

ПРАВИЛА:
- Всегда выполняй код через execute_python, чтобы проверить его работоспособность
- Если код падает с ошибкой — читай stderr, исправляй код и выполняй снова
- Не выдумывай результат выполнения — используй только реальный вывод из execute_python

ФОРМАТ:
- Кратко опиши, что ты делаешь
- Вызови execute_python с кодом
- Проанализируй результат
- Дай финальный ответ с рабочим кодом
"""

# ====================================
# Инициализация LLM
# ===================================


llm = ChatOllama(model=LLM_MODEL, tempfile=TEMPERATURE, num_ctx=4096).bind_tools(
    ALL_TOOLS
)


# ================================
# Узды графа (NODES)
# ==================================
def agent_node(state: AgentState) -> dict:
    """
    Главный узел: вызывает LLM.
    """
    messages = list(state["messages"])

    # БЕЗОПАСНАЯ ПРОВЕРКА:
    # Если список пуст или первый элемент не SystemMessage, добавляем его
    if not messages or not isinstance(messages[0], SystemMessage):
        # Явно приводим к строке и используем именованный аргумент content=
        safe_prompt = str(SYSTEM_PROMPT) if SYSTEM_PROMPT else "Ты полезный ассистент."
        messages = [SystemMessage(content=safe_prompt)] + messages

    # Вызываем LLM
    response = llm.invoke(messages)

    # =====================================
    # qwen часто пишет вызов инструмента JSON-блоком в тексте,
    # а не в response.tool_calls. Без этого граф сразу идёт в END
    # и execute_python никогда не запускается.
    if not getattr(response, "tool_calls", None):
        parsed_calls = _tool_calls_from_text(response.content)
        if parsed_calls:
            response = AIMessage(
                content=response.content or "", tool_calls=parsed_calls
            )
    # =====================================

    return {
        "messages": [response],
        "iteration": state.get("iteration", 0) + 1,
    }


def _balanced_json_objects(text: str) -> list:
    """Вырезает JSON-объекты с вложенными скобками."""
    objects = []
    start = None
    depth = 0
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start : i + 1])
                start = None
    return objects


def _unescape_code(code: str) -> str:
    if "\n" in code:
        return code
    return code.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")


def _tool_calls_from_text(content) -> list:
    """Достаёт вызовы инструментов из текста ответа модели."""
    if not isinstance(content, str) or not content.strip():
        return []

    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.DOTALL)
    blobs = []
    for block in fenced:
        blobs.extend(_balanced_json_objects(block))
    if not blobs:
        blobs = _balanced_json_objects(content)

    calls = []
    for blob in blobs:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        name = data.get("name")
        if not name:
            continue
        args = data.get("arguments", data.get("args", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            continue
        calls.append(
            {
                "name": name,
                "args": args,
                "id": data.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "tool_call",
            }
        )
    return calls


def tool_node(state: AgentState) -> dict:
    """
    Узел выполнения инструментов.
    Берет tool_calls из последнего AIMessage и выполняет их.
    """
    last_message = state["messages"][-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": []}

    tool_responses = []
    tool_dict = {t.name: t for t in ALL_TOOLS}

    # =====================================
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        # =====================================

        # =====================================
        # Модель часто кладёт в JSON последовательности \\n как два символа.
        # Без раскодирования файл состоит из одной строки и падает с SyntaxError.
        if isinstance(tool_args, dict) and isinstance(tool_args.get("code"), str):
            tool_args = dict(tool_args)
            tool_args["code"] = _unescape_code(tool_args["code"])
        # =====================================

        try:
            if tool_name in tool_dict:
                result = tool_dict[tool_name].invoke(tool_args)
            else:
                result = f"ERROR: Инструмент '{tool_name}' не найден"
        except Exception as e:
            result = f"ERROR: {str(e)}"

        print(f"\n▶ {tool_name}\n{result}")

        # ToolMessage с результатом
        tool_responses.append(
            ToolMessage(content=str(result), tool_call_id=tool_call["id"])
        )

    return {"messages": tool_responses}


# ==========================================
# 5. МАРШРУТИЗАЦИЯ (ROUTING)
# ==========================================


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    Решает, куда идти дальше:
    - Если LLM вызвала инструменты → в tool_node
    - Если LLM ответила текстом → в END
    - Если превышен лимит итераций → принудительно в END
    """
    last_message = state["messages"][-1]
    iteration = state.get("iteration", 0)

    # Защита от зацикливания
    if iteration >= MAX_ITER:
        print(f"\n  Достигнут лимит итераций ({MAX_ITER})")
        return "end"

    # Если есть вызовы инструментов — идем в tool_node
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    # Иначе — завершаем
    return "end"


# ==========================================
# 6. СБОРКА ГРАФА
# ==========================================


def build_agent():
    """Создает и компилирует граф агента."""

    workflow = StateGraph(AgentState)

    # Добавляем узлы
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    # Настраиваем ребра
    workflow.set_entry_point("agent")

    # Условное ребро от агента
    workflow.add_conditional_edges(
        "agent", should_continue, {"tools": "tools", "end": END}
    )

    # После инструментов — обратно к агенту (ЦИКЛ!)
    workflow.add_edge("tools", "agent")

    # Компилируем с persistence (для сохранения состояния)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# Глобальный экземпляр агента
agent = build_agent()


def run_agent(user_input: str, thread_id: str = "default"):
    """
    Запускает агента с пользовательским запросом.

    Args:
        user_input: Запрос пользователя
        thread_id: ID сессии (для изоляции диалогов)

    Returns:
        Финальный ответ агента
    """
    config = {"configurable": {"thread_id": thread_id}}

    inputs = {
        "messages": [HumanMessage(content=user_input)],
        "iteration": 0,
    }

    print(f"\n{'=' * 60}")
    print(f"👤 Пользователь: {user_input}")
    print(f"{'=' * 60}")

    # Стриминг событий
    final_response = None
    for event in agent.stream(inputs, config=config, stream_mode="values"):
        last_msg = event["messages"][-1]

        # Показываем ответы агента
        if isinstance(last_msg, AIMessage) and last_msg.content:
            visible = re.sub(
                r"```json\s*.*?```",
                "",
                last_msg.content,
                flags=re.DOTALL,
            ).strip()
            if visible:
                print(f"\n🤖 Агент: {visible}")
            final_response = last_msg.content

    return final_response


if __name__ == "__main__":
    # Пример использования
    result = run_agent(
        "Напиши функцию для вычисления факториала числа и проверь её на числах 5 и 10"
    )
    print(f"\n{'=' * 60}")
    print(f"✅ Финальный ответ:\n{result}")
