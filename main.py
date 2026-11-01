# main.py
from graph import app
from langchain_core.messages import HumanMessage


def run_multi_agent(task: str):
    print(f"\n🚀 Запуск мультиагентной системы для задачи: '{task}'\n")
    print("=" * 60)

    initial_state = {
        "messages": [HumanMessage(content=task)],
        "task": task,
        "current_code": "",
        "test_results": "",
        "documentation": "",
        "status": "planning",
        "iteration": 0,
    }

    # Запускаем граф в режиме стриминга, чтобы видеть работу каждого агента
    for event in app.stream(initial_state, stream_mode="values"):
        current_status = event.get("status", "unknown")
        last_message = event["messages"][-1]

        text = getattr(last_message, "content", "") or ""
        if not isinstance(text, str):
            text = str(text)
        print(f"\n🔄 Текущий статус: [{current_status.upper()}]")
        print(f"🤖 Агент: {text[:300]}...")

        # Если агент вызвал инструменты, покажем это
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tc in last_message.tool_calls:
                print(f"   🔧 Вызов инструмента: {tc['name']}({tc['args']})")

    print("\n" + "=" * 60)
    print(
        "✅ РАБОТА ЗАВЕРШЕНА. Файлы лежат в папке solution: solution.py, test_solution.py, solution.md, plan.txt."
    )


if __name__ == "__main__":
    user_task = """
    Напиши функцию для расчета чисел Фибоначчи до N-го элемента.
    Требования:
    - Используй валидацию входных данных (проверка на положительное целое число)
    - Обработай краевые случаи
    - Добавь подробные комментарии
    """
    run_multi_agent(user_task)
