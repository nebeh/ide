# indexer.py
import os
from pathlib import Path
from typing import List

# httpx не принимает схему socks://. Локальным Ollama и Qdrant этот прокси не нужен.
for _proxy_key in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    if os.environ.get(_proxy_key, "").lower().startswith("socks://"):
        os.environ.pop(_proxy_key, None)

from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
from langchain_text_splitters import RecursiveCharacterTextSplitter, Language
from langchain_ollama import OllamaEmbeddings

# === Конфигурация ===
CODEBASE_PATH = Path("./codebase")
COLLECTION_NAME = "python_codebase"
EMBED_MODEL = "nomic-embed-text"
VECTOR_DIM = 768


def get_python_files(path: Path) -> List[Path]:
    """Рекурсивно находит все Python файлы."""
    return list(path.rglob("*.py"))


def chunk_python_file(file_path: Path) -> List[dict]:
    """Разбивает Python файл на чанки с метаданными."""
    content = file_path.read_text(encoding="utf-8")

    # Используем AST-чанкинг для Python
    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.PYTHON, chunk_size=1000, chunk_overlap=100
    )

    chunks = splitter.split_text(content)

    # Добавляем метаданные к каждому чанку
    result = []
    for i, chunk in enumerate(chunks):
        result.append(
            {
                "content": chunk,
                "metadata": {
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                },
            }
        )

    return result


def index_codebase():
    """Главная функция индексации."""
    print(f"🔍 Сканирование кодовой базы в {CODEBASE_PATH}...")

    # Находим все Python файлы
    files = get_python_files(CODEBASE_PATH)
    print(f" Найдено {len(files)} Python файлов")

    # Чанкуем все файлы
    all_chunks = []
    for file_path in files:
        chunks = chunk_python_file(file_path)
        all_chunks.extend(chunks)
        print(f"  {file_path.name}: {len(chunks)} чанков")

    print(f"\nВсего чанков: {len(all_chunks)}")

    # Инициализируем Qdrant
    client = QdrantClient(host="localhost", port=6333, check_compatibility=False)

    # Создаем коллекцию (если не существует)
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        print(f"Коллекция '{COLLECTION_NAME}' создана")

    # Генерируем эмбеддинги батчами
    embeddings = OllamaEmbeddings(model=EMBED_MODEL)

    BATCH_SIZE = 32
    points = []

    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i : i + BATCH_SIZE]
        texts = [chunk["content"] for chunk in batch]

        print(
            f" Генерация эмбеддингов: {i + 1}-{min(i + BATCH_SIZE, len(all_chunks))}..."
        )
        vectors = embeddings.embed_documents(texts)

        for j, (chunk, vector) in enumerate(zip(batch, vectors)):
            points.append(
                PointStruct(
                    id=i + j,
                    vector=vector,
                    payload={"content": chunk["content"], **chunk["metadata"]},
                )
            )

    # Загружаем в Qdrant
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"\n Индексация завершена! Загружено {len(points)} чанков в Qdrant.")


if __name__ == "__main__":
    index_codebase()
