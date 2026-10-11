import os
import sys
import importlib


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
            sys.exit(1)
        except Exception as e:
            print(f"Error loading devices from source '{clean_name}': {e}")
            sys.exit(1)

        print(f"Source '{clean_name}' yielded {len(source_hosts)} host(s).")
        for item in source_hosts:
            raw_host = item.get("host", "")
            if not raw_host:
                continue
            canonical_key = raw_host.strip().lower()

            if canonical_key not in unique_hosts:
                entry = dict(item)
                entry["sources"] = [clean_name]
                unique_hosts[canonical_key] = entry
            else:
                existing = unique_hosts[canonical_key]
                if clean_name not in existing["sources"]:
                    existing["sources"].append(clean_name)
                # Merge non-empty fields from item into existing
                for k, v in item.items():
                    if k in ("host", "sources"):
                        continue
                    if v is not None and v != "":
                        if k not in existing or existing[k] is None or existing[k] == "":
                            existing[k] = v
                        elif isinstance(existing[k], list) and isinstance(v, list):
                            for sub_item in v:
                                if sub_item not in existing[k]:
                                    existing[k].append(sub_item)

    merged_hosts = list(unique_hosts.values())
    print(f"Total unique hosts across all sources: {len(merged_hosts)}\n")
    return merged_hosts
