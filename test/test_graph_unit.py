import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from src.knowledge.services.upload_graph_service import UploadGraphService

# For backward compatibility with the existing test
GraphDatabase = UploadGraphService


@pytest.mark.asyncio
async def test_txt_add_vector_entity_parsing():
    # Mock driver and session
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Setup mock transaction
    mock_tx = MagicMock()

    def side_effect_execute_write(func, *args, **kwargs):
        return func(mock_tx, *args, **kwargs)

    # Mock execute_read to return empty list (no missing embeddings for this test)
    # The code calls _get_nodes_without_embedding which returns [record['name']]
    # If we return [], it means all nodes have embeddings or none found.
    # Actually, the code checks:
    # nodes_without_embedding = session.execute_read(_get_nodes_without_embedding, all_entities)
    # Let's mock it to return empty list so we skip embedding generation loop which simplifies test
    mock_session.execute_read.return_value = []

    mock_session.execute_write.side_effect = side_effect_execute_write

    # Mock embedding model
    with patch("src.models.select_embedding_model") as mock_select_model:
        mock_embed_model = MagicMock()
        mock_select_model.return_value = mock_embed_model

        # Instantiate GraphDatabase with mocked driver
        # We also need to patch Neo4jConnectionManager in the init
        with patch("src.knowledge.services.upload_graph_service.Neo4jConnectionManager") as mock_connection_manager:
            # Mock the connection manager to return our mocked driver
            mock_connection_manager.return_value.driver = mock_driver
            mock_connection_manager.return_value.status = "open"

            gd = GraphDatabase(mock_connection_manager.return_value)
            # Manually set properties just in case init didn't work as expected due to other mocks
            gd.driver = mock_driver
            gd.status = "open"
            gd.embed_model_name = "test_model"  # avoid config check issues if possible

            # Mock config to match
            with patch("src.config.embed_model", "test_model"):
                with patch("src.config.embed_model_names", {"test_model": MagicMock(dimension=1024)}):
                    # Test data: Mixed format
                    triples = [
                        # Legacy format
                        {"h": "A", "r": "KNOWS", "t": "B"},
                        # Extended format
                        {
                            "h": {"name": "C", "age": 30},
                            "r": {"type": "LIKES", "weight": 0.8},
                            "t": {"name": "D", "role": "User"},
                        },
                    ]

                # Run the method
                await gd.txt_add_vector_entity(triples)

                # Verify calls to mock_tx.run
                merge_calls = []
                for call in mock_tx.run.call_args_list:
                    args, kwargs = call
                    query = args[0] if args else kwargs.get("query", "")
                    if "MERGE (h:Entity:Upload" in query:
                        # The args are passed as kwargs to run: h_name=..., etc.
                        merge_calls.append(kwargs)

                assert len(merge_calls) == 2, f"Expected 2 merge calls, got {len(merge_calls)}"

                # Call 1 (Legacy)
                call1 = merge_calls[0]
                assert call1["h_name"] == "A"
                assert call1["h_props"] == {}
                assert call1["t_name"] == "B"
                assert call1["t_props"] == {}
                assert call1["r_type"] == "KNOWS"
                assert call1["r_props"] == {}

                # Call 2 (Extended)
                call2 = merge_calls[1]
                assert call2["h_name"] == "C"
                assert call2["h_props"] == {"age": 30}
                assert call2["t_name"] == "D"
                assert call2["t_props"] == {"role": "User"}
                assert call2["r_type"] == "LIKES"
                assert call2["r_props"] == {"weight": 0.8}

                print("Verification passed!")
