"""This module defines any initial processes to run when the robot starts."""

import ast
import glob
import json
import os
import shutil
import uuid
from datetime import datetime

import pandas as pd
import sqlalchemy
from mbu_dev_shared_components.utils.fernet_encryptor import Encryptor
from mbu_msoffice_integration.sharepoint_class import Sharepoint
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection

from robot_framework import config


def initialize(orchestrator_connection: OrchestratorConnection) -> None:
    """Primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    process_args = json.loads(orchestrator_connection.process_arguments)
    naeste_agent_arg = process_args["naeste_agent"]

    delete_all_files_in_path(config.PATH)
    filename = fetch_files(folder_name=config.DOCUMENT_FOLDER)
    data_df = load_excel_data(filename)
    processed_df = process_data(data_df, naeste_agent_arg, filename)
    approved_df = processed_df[processed_df["is_godkendt"]]
    upload_to_queue(approved_df, orchestrator_connection)


def delete_all_files_in_path(path):
    """Delete all files and directories in the given path."""
    # Check if the path exists and create it if it doesn't
    if not os.path.exists(path):
        print(f"Directory does not exist. Creating: {path}")
        os.makedirs(path)

    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)

        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)
                print(f"File deleted: {file_path}")
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
                print(f"Directory deleted: {file_path}")
        except (OSError, shutil.Error) as e:
            print(f"Failed to delete {file_path}. Reason: {e}")


def fetch_files(folder_name) -> None:
    """Download Excel files from SharePoint to the specified path."""
    if not os.path.exists(config.PATH):
        os.makedirs(config.PATH)

    sharepoint = Sharepoint(
        **config.SHAREPOINT_CREDS,
        document_library=config.DOCUMENT_LIBRARY,
        site_url=config.SHAREPOINT_SITE_URL,
        site_name=config.SHAREPOINT_SITE_NAME,
    )

    files = sharepoint.fetch_files_list(folder_name)

    # sharepoint.ctx.load(files)
    # sharepoint.ctx.execute_query()

    if not files:
        print("No files found in the specified SharePoint folder.")

    filename = None

    for file in files:
        if file["Name"].endswith(".xlsx"):
            filename = file["Name"]
            download_path_file = os.path.join(config.PATH, file["Name"])
            with open(download_path_file, "wb") as local_file:
                file_content = sharepoint.fetch_file_using_open_binary(
                    filename, folder_name
                )
                local_file.write(file_content)
            print(f"Downloaded: {file['Name']} to {download_path_file}")

    return filename


def load_excel_data(filename) -> pd.DataFrame:
    """Load the first Excel file matching the pattern from the directory."""
    print("Loading Excel data...")
    excel_files = glob.glob(os.path.join(config.PATH, filename))
    if not excel_files:
        raise FileNotFoundError("File not found in the specified folder.")

    file_to_read = excel_files[0]
    df = pd.read_excel(file_to_read)
    print(f"Data loaded from: {file_to_read}")
    return df


def extract_url_from_attachments(attachments_str: str) -> str:
    """Extract the URL from the attachments string."""
    if isinstance(attachments_str, str):
        start_index = attachments_str.find("https://")
        if start_index != -1:
            end_index = attachments_str.find("'", start_index)
            if end_index != -1 and end_index > start_index:
                return attachments_str[start_index:end_index]
    return pd.NA


def extract_months_and_year(test_str):
    """Extract months and year from the test string."""
    month_map = {
        "January": "Januar",
        "February": "Februar",
        "March": "Marts",
        "April": "April",
        "May": "Maj",
        "June": "Juni",
        "July": "Juli",
        "August": "August",
        "September": "September",
        "October": "Oktober",
        "November": "November",
        "December": "December",
    }
    data = ast.literal_eval(test_str)
    months = set()
    year = None

    for entry in data:
        if isinstance(entry, dict) and "dato" in entry:
            date_str = entry["dato"]
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            month_name = date_obj.strftime("%B")
            months.add(month_map.get(month_name, month_name))
            year = date_obj.year

    sorted_months = sorted(months, key=lambda x: list(month_map.values()).index(x))

    month_str = "/".join(sorted_months)
    result = f"{month_str} {year}"

    return result


def process_data(df: pd.DataFrame, naeste_agent: str, filename) -> pd.DataFrame:
    """Process the data and return a DataFrame with the required format."""
    encryptor = Encryptor()
    processed_data = []

    for _, row in df.iterrows():
        month_year = extract_months_and_year(row["test"])
        cpr_nr = (
            str(row["cpr_nr_paaanden"])
            if not pd.isnull(row["cpr_nr_paaanden"])
            else str(row["cpr_nr"])
        )
        attachments_str = str(row.get("attachments", ""))
        url = extract_url_from_attachments(attachments_str)
        skoleliste = (
            str(row["skoleliste"]).lower() if not pd.isnull(row["skoleliste"]) else ""
        )
        barnets_navn = str(row["barnets_navn"])

        psp_value = determine_psp_value(skoleliste, row)

        encrypted_cpr = encryptor.encrypt(cpr_nr).decode("utf-8")

        # Ensure that the beloeb value is a string, replace all . with , and keep only the last comma
        beloeb_value = (
            row["aendret_beloeb_i_alt"]
            if not pd.isnull(row["aendret_beloeb_i_alt"])
            else row["beloeb_i_alt"]
        )
        if pd.notnull(beloeb_value):
            # Replace all periods with commas
            beloeb_value = str(beloeb_value).replace(".", ",")
            # If there are multiple commas, keep only the last one
            if beloeb_value.count(",") > 1:
                parts = beloeb_value.split(",")
                # Join all but the last part without commas, then add the last part with a comma
                beloeb_value = "".join(parts[:-1]) + "," + parts[-1]

        new_row = {
            "filename": filename,
            "cpr_encrypted": encrypted_cpr,
            "barnets_navn": barnets_navn,
            "beloeb": beloeb_value,
            "reference": month_year,
            "arts_konto": "40430002",
            "psp": psp_value,
            "posteringstekst": f"Egenbefordring {month_year}",
            "naeste_agent": naeste_agent,
            "attachment": url,
            "uuid": row.get("uuid", pd.NA),
            "godkendt_af": row.get("godkendt_af", pd.NA),
            "skole": row["skriv_dit_barns_skole_eller_dagtilbud"]
            if not pd.isnull(row["skriv_dit_barns_skole_eller_dagtilbud"])
            else row["skoleliste"],
            "is_godkendt": "x" in str(row.get("godkendt", "")).lower(),
            "evt_kommentar": row.get("evt_kommentar"),
        }

        if new_row.get("uuid") not in (
            "8a92a866-6841-4237-a3a2-0287af0cc4ad",
            "0d313e6c-4687-47af-a577-053158de53c5",
            "9be4b2c3-e7e3-4888-9bf0-47f9b37650e0",
            "5416e4dd-bdee-4b58-a93a-6ee36f9a35d8",
            "42091f88-444c-4d18-9dd4-3a5a3a7c271f",
            "9d18fd36-683d-4c76-a9ef-ae8051af54fa",
            "8578ee81-148f-4ba3-bbce-bc05a88264c8",
            "b9379949-1d6e-4bd3-8b32-88fa766be227",
            "f7f09cf4-1240-4351-8fa3-75b80f5f03fb",
        ):
            processed_data.append(new_row)

    df_processed = pd.DataFrame(processed_data)

    return df_processed


def determine_psp_value(skoleliste: str, row: pd.Series) -> str:
    """Determine PSP value based on school list."""

    if (
        "langagerskolen" in skoleliste
        or "751090#1830" in skoleliste
        or "751090#2471" in skoleliste
    ):
        return "XG-5240220808-00004"

    if (
        "stensagerskolen" in skoleliste
        or "751903#591" in skoleliste
        or "751903#2521" in skoleliste
    ):
        return "XG-5240220808-00005"

    if not pd.isnull(row["skriv_dit_barns_skole_eller_dagtilbud"]):
        return "XG-5240220808-00006"

    # Default PSP value
    return "XG-5240220808-00003"


def make_unique_references(references: list) -> list:
    """Generate unique references by appending UUIDs."""
    return [f"{ref}_{uuid.uuid4().hex}" for ref in references]


def upload_to_queue(
    result_df: pd.DataFrame, orchestrator_connection: OrchestratorConnection
) -> None:
    """Upload the processed data to the orchestrator queue."""
    queue_data = [
        json.dumps(data, ensure_ascii=False, default=str)
        for data in result_df.to_dict(orient="records")
    ]
    queue_references = [str(row["posteringstekst"]) for _, row in result_df.iterrows()]
    unique_references = make_unique_references(queue_references)

    try:
        print("Uploading data to queue...")
        orchestrator_connection.bulk_create_queue_elements(
            config.QUEUE_NAME, references=unique_references, data=queue_data
        )
        print("Data uploaded to queue successfully.")
        orchestrator_connection.log_trace("Data uploaded to queue.")

    except sqlalchemy.exc.IntegrityError as ie:
        print(f"IntegrityError: {ie.orig}")

    except (ValueError, TypeError) as e:
        print(f"Error occurred: {e}")
