from pathlib import Path

from langchain_community.document_loaders import UnstructuredEmailLoader


def load_email(filepath):
    loader = UnstructuredEmailLoader(filepath)
    return loader.load()

if __name__ == "__main__":
    documents = load_email("C:\\Users\\Anish Kumar Verma\\PycharmProjects\\Notifier\\Ingestion\\fetched_emails\\26638.eml")

    for document in documents:
        print(document.page_content)
        print(document.metadata)