# state.py
from typing import Annotated, TypedDict, Sequence
from langchain_core.messages import BaseMessage
import operator


class MultiAgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    task: str  # Исходная задача пользователя
    current_code: str  # Последняя версия кода
    test_results: str  # Результат запуска тестов (успех или лог ошибки)
    documentation: str  # Финальная документация
    status: str  # Текущий этап: "planning", "coding", "testing", "documenting", "done"
    iteration: int  # Счетчик циклов (защита от зацикливания)
