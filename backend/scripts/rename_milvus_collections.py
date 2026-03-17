import os

from pymilvus import Collection, connections, utility


def get_collection_info(collection_name, alias):
    """Safely gets a collection object and its number of entities."""
    try:
        collection = Collection(collection_name, using=alias)
        collection.load()
        return collection, collection.num_entities
    except Exception as e:
        print(f"Error getting info for collection '{collection_name}': {e}")
        return None, 0


def rename_and_resolve_duplicates():
    """
    Connects to Milvus, renames collections from 'kb_kb_' to 'kb_',
    and resolves duplicates by keeping the collection with more rows.
    """
    milvus_uri = os.getenv("MILVUS_URI") or "http://localhost:19530"
    milvus_token = os.getenv("MILVUS_TOKEN") or ""
    connection_alias = "rename_script"

    try:
        print(f"Connecting to Milvus at {milvus_uri}...")
        connections.connect(alias=connection_alias, uri=milvus_uri, token=milvus_token)
        print("Successfully connected to Milvus.")

        all_collections = utility.list_collections(using=connection_alias)
        collections_to_rename = [c for c in all_collections if c.startswith("kb_kb_")]

        if not collections_to_rename:
            print("No collections with the prefix 'kb_kb_' found. Nothing to do.")
            return

        print(f"Found {len(collections_to_rename)} collections with 'kb_kb_' prefix to process.")

        for old_name in collections_to_rename:
            new_name = old_name.replace("kb_kb_", "kb_", 1)
            try:
                print(f"Attempting to rename '{old_name}' to '{new_name}'...")
                utility.rename_collection(old_name, new_name, using=connection_alias)
                print(f"Successfully renamed '{old_name}' to '{new_name}'.")
            except Exception as e:
                # Check if it's a duplicate name error
                if "duplicated new collection name" in str(e):
                    print(f"Rename failed: Target collection '{new_name}' already exists. Resolving duplicate...")

                    # Get info for both collections
                    old_coll, old_count = get_collection_info(old_name, connection_alias)
                    new_coll, new_count = get_collection_info(new_name, connection_alias)

                    print(f"Comparing row counts: '{old_name}' ({old_count} rows) vs '{new_name}' ({new_count} rows).")

                    if old_count > new_count:
                        print(f"'{old_name}' has more rows. Deleting '{new_name}' and retrying rename.")
                        utility.drop_collection(new_name, using=connection_alias)
                        print(f"Dropped collection '{new_name}'.")
                        # Retry renaming
                        utility.rename_collection(old_name, new_name, using=connection_alias)
                        print(f"Successfully renamed '{old_name}' to '{new_name}'.")
                    else:
                        print(f"'{new_name}' has more or equal rows. Deleting '{old_name}'.")
                        utility.drop_collection(old_name, using=connection_alias)
                        print(f"Dropped collection '{old_name}'.")
                else:
                    print(f"An unexpected error occurred while renaming '{old_name}': {e}")

        print("\nProcess finished.")

    except Exception as e:
        print(f"A critical error occurred: {e}")
    finally:
        if connection_alias in connections.list_connections():
            connections.disconnect(connection_alias)
            print("Disconnected from Milvus.")


if __name__ == "__main__":
    rename_and_resolve_duplicates()
