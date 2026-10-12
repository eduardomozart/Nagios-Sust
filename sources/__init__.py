import os
import sys
import importlib
from utils.exit_codes import ERR_SOURCE_NOT_FOUND, ERR_SOURCE_LOAD_ERROR


def get_supported_sources():
    """
    Returns a sorted list of all available source module names in sources/.
    """
    sources_dir = os.path.dirname(os.path.abspath(__file__))
    available = []
    if os.path.exists(sources_dir):
        for fname in os.listdir(sources_dir):
            if fname.endswith(".py") and not fname.startswith("_"):
                available.append(fname[:-3])
    return sorted(available)


def load_unique_hosts(config, source_options=None):
    """
    Ingests hosts from all configured sources in config['device_sources'].
    Deduplicates by canonical hostname (case-insensitive) and merges
    attributes from overlapping sources, tracking source provenance in 'sources'.
    """
    if source_options is None:
        source_options = {}

    sources = config.get("device_sources", [])
    unique_hosts = {}

    for src_name in sources:
        clean_name = src_name.strip().lower()
        print(f"Loading devices from source: '{clean_name}'...")
        try:
            source_module = importlib.import_module(f"sources.{clean_name}")
            source_hosts = source_module.get_hosts(config, source_options)
        except ImportError:
            print(f"Error: Device source '{clean_name}' not found in sources/")
            sys.exit(ERR_SOURCE_NOT_FOUND)
        except Exception as e:
            print(f"Error loading devices from source '{clean_name}': {e}")
            sys.exit(ERR_SOURCE_LOAD_ERROR)

        print(f"Source '{clean_name}' yielded {len(source_hosts)} host(s).")
        for item in source_hosts:
            raw_host = item.get("host", "")
            if not raw_host:
                continue
            canonical_key = raw_host.strip().lower()

            # Extract source-specific attributes
            source_metadata = {k: v for k, v in item.items() if k not in ("host", "sources")}

            if canonical_key not in unique_hosts:
                entry = {
                    "host": item["host"],
                    "sources": [clean_name],
                    clean_name: source_metadata,
                }
                unique_hosts[canonical_key] = entry
            else:
                existing = unique_hosts[canonical_key]
                if "sources" not in existing or not isinstance(existing["sources"], list):
                    existing["sources"] = []
                if clean_name not in existing["sources"]:
                    existing["sources"].append(clean_name)
                existing[clean_name] = source_metadata

    merged_hosts = list(unique_hosts.values())
    print(f"Total unique hosts across all sources: {len(merged_hosts)}\n")
    return merged_hosts
