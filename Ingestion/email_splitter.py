from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from Ingestion.email_loader import load_email
except ModuleNotFoundError:
    from email_loader import load_email


def split_emails(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )

    return splitter.split_documents(documents)


if __name__ == "__main__":
    documents = load_email("C:\\Users\\Anish Kumar Verma\\PycharmProjects\\Notifier\\Ingestion\\fetched_emails\\26638.eml")
    chunks = split_emails(documents)

    print("Documents:", len(documents))
    print("Chunks:", len(chunks))

    for chunk in chunks[:3]:
        print("\n--- CHUNK ---")
        print(chunk.page_content)
        print(chunk.metadata)