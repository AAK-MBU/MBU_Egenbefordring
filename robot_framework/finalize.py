"""This module defines any finalizing processes to run when the robot starts."""

import os
from datetime import datetime
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueStatus
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from robot_framework import config
from robot_framework.subprocesses.notify import send_mail


def finalize(orchestrator_connection: OrchestratorConnection) -> None:
    """Do the primary process of the robot."""
    orchestrator_connection.log_trace("Running process.")
    service_konto_credential = orchestrator_connection.get_credential("SvcRpaMBU002")
    username = service_konto_credential.username
    password = service_konto_credential.password
    update_sharepoint(orchestrator_connection, username, password)
    send_mail(orchestrator_connection=orchestrator_connection)


def update_sharepoint(orchestrator_connection: OrchestratorConnection, username, password):
    """Update the SharePoint folders."""
    orchestrator_connection.log_trace("Updating SharePoint folders.")

    # Check if the provided path_arg is a directory
    if not os.path.isdir(config.PATH):
        orchestrator_connection.log_trace(f"The provided path is not a directory: {config.PATH}")
        return

    # Get the list of files in the provided directory
    excel_files = [f for f in os.listdir(config.PATH) if f.endswith(('.xlsx', '.xls'))]

    if not excel_files:
        orchestrator_connection.log_trace(f"No Excel files found in the directory: {config.PATH}")
        return

    # Process each Excel file found
    for filename in excel_files:
        file_path = os.path.join(config.PATH, filename)

        if os.path.isfile(file_path):  # Ensure it's a file
            failed_elements = orchestrator_connection.get_queue_elements(
                config.QUEUE_NAME,
                status=QueueStatus.FAILED,
                from_date=datetime.today(),
                to_date=datetime.today())
            if failed_elements:
                folder_dest = "Fejlet"
                orchestrator_connection.log_trace(f"Moving Excel file and failed attachments to the '{folder_dest}' folder.")
                folder_name = os.path.splitext(filename)[0]
                upload_file_to_sharepoint(username, password, config.PATH, filename, folder_dest)
                upload_folder_to_sharepoint(username, password, folder_name, folder_dest)
            else:
                folder_dest = "Behandlet"
                orchestrator_connection.log_trace(f"Uploading Excel file to the '{folder_dest}' folder.")
                upload_file_to_sharepoint(username, password, config.PATH, filename, folder_dest)

            # Optionally, delete the file from SharePoint here if needed
            delete_file_from_sharepoint(username, password, filename)

    orchestrator_connection.log_trace(f"SharePoint folder '{folder_dest}' updated.")
    orchestrator_connection.folder_dest = folder_dest


def upload_file_to_sharepoint(username: str, password: str, path: str, excel_filename: str, sharepoint_folder_name: str) -> None:
    """Upload a file to SharePoint."""
    ctx = ClientContext(config.SHAREPOINT_SITE_URL).with_credentials(UserCredential(username, password))
    target_folder_url = f"/{config.SHAREPOINT_REL_URL}/{config.DOCUMENT_LIBRARY}/{sharepoint_folder_name}"
    target_folder = ctx.web.get_folder_by_server_relative_url(target_folder_url)
    file_path = os.path.join(path, excel_filename)
    with open(file_path, "rb") as file_content:
        target_folder.upload_file(excel_filename, file_content).execute_query()

    print(f"File '{excel_filename}' has been uploaded successfully to SharePoint in '{sharepoint_folder_name}'.")


def upload_folder_to_sharepoint(username: str, password: str, folder_name: str, sharepoint_folder_name: str) -> None:
    """Upload a folder and its contents to SharePoint."""
    ctx = ClientContext(config.SHAREPOINT_SITE_URL).with_credentials(UserCredential(username, password))
    target_folder_url = f"/{config.SHAREPOINT_REL_URL}/{config.DOCUMENT_LIBRARY}/{sharepoint_folder_name}"
    ctx.web.folders.add(target_folder_url).execute_query()
    print(f"Folder '{folder_name}' created in SharePoint.")

    local_folder_path = os.path.join(config.PATH, folder_name)
    updated_sharepoint_folder_name = f"{sharepoint_folder_name}/{folder_name}"

    if os.path.exists(local_folder_path):
        for file_name in os.listdir(local_folder_path):
            file_full_path = os.path.join(local_folder_path, file_name)
            if os.path.isfile(file_full_path):
                upload_file_to_sharepoint(username, password, local_folder_path, file_name, updated_sharepoint_folder_name)

    print(f"Folder '{folder_name}' and its contents have been uploaded successfully to SharePoint.")


def delete_file_from_sharepoint(username: str, password: str, file_name: str) -> None:
    """Delete a file from SharePoint."""
    ctx = ClientContext(config.SHAREPOINT_SITE_URL).with_credentials(UserCredential(username, password))
    target_file_url = f"/{config.SHAREPOINT_REL_URL}/{config.DOCUMENT_LIBRARY}/{file_name}"
    try:
        file = ctx.web.get_file_by_server_relative_url(target_file_url)
        file.delete_object()
        ctx.execute_query()

        print(f"File '{file_name}' has been deleted successfully from SharePoint.")
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error deleting file '{file_name}': {e}")
