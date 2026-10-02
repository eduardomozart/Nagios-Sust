import pdfplumber

def parse_nagios_pdf(pdf_path):
    alerts = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table:
                    continue
                
                # Identify the header row
                header_idx = -1
                for i, row in enumerate(table):
                    if row and len(row) > 1:
                        # Check if the initial columns are Host and Service (as in the Nagios report)
                        row_str = " ".join([str(c) for c in row if c])
                        if "Host" in row_str and "Service" in row_str:
                            header_idx = i
                            break
                
                if header_idx != -1:
                    # Extract data
                    for row in table[header_idx + 1:]:
                        if not row or not row[0]:
                            continue
                        
                        host_raw = str(row[0]).strip()
                        # Extract the first line in case it's broken
                        host_cleaned = host_raw.split('\n')[0].strip()
                        
                        # Safely grab the other columns
                        service = str(row[1]).replace('\n', ' ').strip() if len(row) > 1 else ""
                        status = str(row[2]).replace('\n', ' ').strip() if len(row) > 2 else ""
                        
                        if host_cleaned:
                            alerts.append({
                                "host": host_cleaned,
                                "service": service,
                                "status": status,
                                "raw_host": host_raw
                            })
                            
    # Return a deduplicated list by host (so we only run once per equipment)
    unique_hosts = {}
    for alert in alerts:
        if alert["host"] not in unique_hosts:
            unique_hosts[alert["host"]] = alert
            
    return list(unique_hosts.values())
