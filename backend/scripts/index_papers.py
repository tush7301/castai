from app.services.vector_store import VectorStore


def main() -> None:
    store = VectorStore()
    result = store.index_papers()
    print(result)


if __name__ == "__main__":
    main()
