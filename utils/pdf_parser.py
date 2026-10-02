import pdfplumber

def parse_nagios_pdf(pdf_path):
    alerts = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                for row in table:
                    if not row:
                        continue
                        
                    # The host is typically in the first or second column
                    host_raw = str(row[0]).strip() if row[0] else ""
                    if not host_raw and len(row) > 1:
                        host_raw = str(row[1]).strip() if row[1] else ""
                        
                    if not host_raw:
                        continue
                        
                    # Clean up the host name (Nagios sometimes wraps text with \n)
                    host_cleaned = host_raw.replace('\n', '')
                    
                    # Ignore headers and generic numeric counters from the report header
                    if len(host_cleaned) < 3 or host_cleaned in ["Host", "Service", "Status"]:
                        continue
                    if host_cleaned.isdigit():
                        continue
                        
                    # Try to guess status just for metadata
                    status = ""
                    for col in row:
                        col_str = str(col).strip().upper() if col else ""
                        if col_str in ["CRITICAL", "WARNING", "UNKNOWN", "OK"]:
                            status = col_str
                            break
                            
                    alerts.append({
                        "host": host_cleaned,
                        "service": "",
                        "status": status,
                        "raw_host": host_raw
                    })
                            
    # Return a deduplicated list by host (so we only run once per equipment)
    unique_hosts = {}
    for alert in alerts:
        if alert["host"] not in unique_hosts:
            unique_hosts[alert["host"]] = alert
            
    return list(unique_hosts.values())
