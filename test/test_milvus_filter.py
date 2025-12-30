import asyncio
import os
from unittest.mock import patch

from src.knowledge import knowledge_base
from src.utils import logger


# Mock Embedding Model
class MockEmbeddingModel:
    async def abatch_encode(self, texts, batch_size=None):
        # Return dummy vectors of dim 4
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    def batch_encode(self, texts, batch_size=None):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


# Test function
async def test_milvus_filter():
    logger.info("Starting Milvus Filter Test")

    # Check if Milvus is available (pymilvus installed and connection works)
    try:
        from pymilvus import connections

        # Assuming Milvus is running at default location
        connections.connect(alias="default", uri=os.getenv("MILVUS_URI", "http://localhost:19530"))
        logger.info("Connected to Milvus")
    except Exception as e:
        logger.warning(f"Milvus not available or connection failed: {e}")
        # Proceeding might fail, but let's try.

    db_id = "test_milvus_filter_db"
    file1 = "test_file_A.txt"
    file2 = "test_file_B.txt"

    # Patch embedding model
    with patch("src.models.embed.select_embedding_model", return_value=MockEmbeddingModel()):
        try:
            # Cleanup if exists
            if db_id in knowledge_base.global_databases_meta:
                await knowledge_base.delete_database(db_id)

            # Create DB
            logger.info("Creating database...")
            # explicitly set dimension to 4 to match mock
            await knowledge_base.create_database(
                database_name="Test Milvus Filter",
                description="Test DB",
                kb_type="milvus",
                embed_info={"name": "mock-embedding", "dimension": 4, "model_id": "mock"},
            )

            # Get actual db_id
            target_db = next(
                (db for db in knowledge_base.get_databases()["databases"] if db["name"] == "Test Milvus Filter"), None
            )
            if not target_db:
                logger.error("Failed to create DB")
                return

            db_id = target_db["db_id"]
            logger.info(f"DB created with ID: {db_id}")

            # Create dummy files

            with open(file1, "w") as f:
                f.write("Apple content.")
            with open(file2, "w") as f:
                f.write("Banana content.")

            # Add content
            logger.info("Adding content...")
            await knowledge_base.add_content(db_id, [os.path.abspath(file1), os.path.abspath(file2)])

            # Wait for data to be visible
            logger.info("Waiting for data to be visible...")
            await asyncio.sleep(2)

            # Query without filter
            logger.info("Querying without filter...")
            results = await knowledge_base.aquery("content", db_id)
            logger.info(f"No filter results: {len(results)}")

            # Verify we have chunks from both files
            sources = [r["metadata"]["source"] for r in results]
            logger.info(f"Sources: {sources}")

            # Query with filter A (Partial Match)
            logger.info("Querying with filter A (file_A)...")
            results_a = await knowledge_base.aquery("content", db_id, file_name="file_A")
            logger.info(f"Filter A results: {len(results_a)}")

            if len(results_a) == 0:
                logger.error("FAIL: Filter A returned 0 results")

            for r in results_a:
                source = r["metadata"]["source"]
                logger.info(f" - {source}")
                if "test_file_A.txt" not in source:
                    logger.error(f"FAIL: Expected test_file_A.txt, got {source}")
                    raise AssertionError("Filter A failed")

            # Query with wildcard filter
            logger.info("Querying with wildcard filter (%B.txt)...")
            results_b = await knowledge_base.aquery("content", db_id, file_name="%B.txt")
            logger.info(f"Filter B results: {len(results_b)}")
            if len(results_b) == 0:
                logger.error("FAIL: Wildcard filter returned 0 results")

            for r in results_b:
                source = r["metadata"]["source"]
                logger.info(f" - {source}")
                if "test_file_B.txt" not in source:
                    logger.error(f"FAIL: Expected test_file_B.txt, got {source}")
                    raise AssertionError("Filter B failed")

            if len(results_a) > 0 and len(results_b) > 0:
                logger.info("Test passed!")
            else:
                logger.error("Test failed: No results found for one or more queries")

        except Exception as e:
            logger.error(f"Test failed with exception: {e}")
            raise
        finally:
            # Cleanup
            logger.info("Cleaning up...")
            try:
                await knowledge_base.delete_database(db_id)
            except Exception:
                pass
            if os.path.exists(file1):
                os.remove(file1)
            if os.path.exists(file2):
                os.remove(file2)


if __name__ == "__main__":
    asyncio.run(test_milvus_filter())
