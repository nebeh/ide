"""
Простой интерфейс для AI-агента.
"""

from agent import run_agent


def main():
    print("\n🤖 AI-агент для написания кода")
    print("Введите 'exit' для выхода\n")

    while True:
        try:
            user_input = input("\nВы: ").strip()

            if user_input.lower() == "exit":
                print("До свидания! 👋")
                break

            if not user_input:
                continue

            # Запускаем агента
            response = run_agent(user_input)

            print(f"\n{'=' * 60}")
        # print(f"✅ Агент: {response}")

        except KeyboardInterrupt:
            print("\n\nПрервано пользователем")
            break
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
