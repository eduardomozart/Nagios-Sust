import os
import sys
from utils.pdf_parser import parse_nagios_pdf
from utils.dialog import open_file_dialog
from utils.airwave import filter_device_name


def get_pdf_file_path(default_path):
    if os.path.exists(default_path):
        return default_path

    print(f"Warning: PDF file '{os.path.basename(default_path)}' not found.")
    print("Please select the PDF file from the file explorer dialog...")

    file_path = open_file_dialog(
        title="Select Nagios Report PDF",
        file_filter="PDF files (*.pdf)\0*.pdf\0All files (*.*)\0*.*\0\0",
    )

    if not file_path:
        print("No file selected. Exiting.")
        sys.exit(1)

    return file_path


def get_hosts(config, options=None):
    """
    Ingests hosts and alerts from a Nagios Service Status PDF report.
    """
    base_dir = options.get("base_dir", os.getcwd()) if options else os.getcwd()
    pdf_cfg = config.get("nagios_pdf", {})
    pdf_name = pdf_cfg.get("report_file", "report.pdf")

    pdf_default_path = os.path.join(base_dir, pdf_name)

    print(f"Checking for report file: {pdf_name}...")
    pdf_path = get_pdf_file_path(pdf_default_path)

    print(f"Parsing PDF: {pdf_path}")
    try:
        alerts = parse_nagios_pdf(pdf_path)
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        sys.exit(1)

    # Optional host_filter applied to PDF extracted hosts
    host_filter = pdf_cfg.get("host_filter")
    if host_filter:
        alerts = [a for a in alerts if filter_device_name(a.get("host"), host_filter)]

    print(f"Found {len(alerts)} unique hosts in the PDF.")
    return alerts
