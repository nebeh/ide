# graph.py
from langgraph.graph import StateGraph, END
from state import MultiAgentState
from agents import architect_node, coder_node, tester_node, documenter_node
from tools import file_is_valid, safe_path


def route_after_tester(state: MultiAgentState) -> str:
    """
    Анализирует последние сообщения, чтобы понять, прошли ли тесты.
    """
    last_msg = str(state["messages"][-1].content or "").lower()
    iteration = state.get("iteration", 0)
    if file_is_valid(safe_path("solution.py"), "solution.py") and file_is_valid(
        safe_path("test_solution.py"), "test_solution.py"
    ):
        return "documenter"

    # Защита от бесконечного цикла (максимум 3 попытки исправления)
    if iteration > 4:
        return "documenter"  # Принудительно завершаем, даже с ошибками

    # Ключевые слова успеха
    if (
        "тесты пройдены" in last_msg
        or "passed" in last_msg
        or "exit code: 0" in last_msg
    ):
        return "documenter"
    else:
        # Если есть ошибки, возвращаемся к кодеру (или архитектору, если ошибка критическая)
        # Для простоты возвращаем кодеру, добавив в контекст сообщение об ошибке
        return "coder"


def build_multi_agent_graph():
    workflow = StateGraph(MultiAgentState)

    # 1. Добавляем узлы
    workflow.add_node("architect", architect_node)
    workflow.add_node("coder", coder_node)
    workflow.add_node("tester", tester_node)
    workflow.add_node("documenter", documenter_node)

    # 2. Настраиваем линейные связи
    workflow.set_entry_point("architect")
    workflow.add_edge("architect", "coder")
    workflow.add_edge("coder", "tester")

    # 3. Настраиваем условную связь после тестирования
    workflow.add_conditional_edges(
        "tester",
        route_after_tester,
        {
            "coder": "coder",  # ЦИКЛ: Возврат на доработку
            "documenter": "documenter",  # УСПЕХ: Идем писать документацию
        },
    )

    # 4. Завершение
    workflow.add_edge("documenter", END)

    # Компилируем
    return workflow.compile()


# Глобальный экземпляр графа
app = build_multi_agent_graph()
