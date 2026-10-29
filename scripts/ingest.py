"""Index the bundled incident corpus into persistent Chroma."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from incidentiq.retrieval import ingest_corpus  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(__file__).resolve().parents[1] / "corpus")
    parser.add_argument("--chroma-path", type=Path, default=None)
    args = parser.parse_args()
    documents, chunks = ingest_corpus(args.corpus, args.chroma_path)
    print(f"Indexed {documents} documents and {chunks} chunks")


if __name__ == "__main__":
    main()
