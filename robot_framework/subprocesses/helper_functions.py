"""Module with helper functions"""
import json
import os
import glob
import pandas as pd
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from mbu_dev_shared_components.utils.db_stored_procedure_executor import execute_stored_procedure

from robot_framework.config import PATH


def handle_post_process(failed, queue_element, orchestrator_connection: OrchestratorConnection, db_status):
    """Update the Excel file with the status of the element."""
    element_data = json.loads(queue_element.data)
    uuid = element_data['uuid']
    excel_filename = element_data['filename']
    connection_string = orchestrator_connection.get_constant("DbConnectionString").value

    excel_files = glob.glob(os.path.join(PATH, excel_filename))
    if not excel_files:
        raise FileNotFoundError(f"{excel_filename} not found in {PATH}.")

    file_to_read = excel_files[0]
    df = pd.read_excel(file_to_read, engine='openpyxl')
    df = ensure_columns(df)
    update_dataframe(df, uuid, failed)

    with pd.ExcelWriter(file_to_read, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)

    execute_stored_procedure(
        connection_string,
        "journalizing.sp_update_status",
        db_status
    )
    orchestrator_connection.log_trace(f"Element status updated to {'failed' if failed else 'succeeded'} in Excel file")


def ensure_columns(df: pd.DataFrame):
    """Ensure that the Excel file has the necessary columns."""
    for col in ['behandlet_fejl', 'behandlet_ok']:
        if col not in df.columns:
            df[col] = ''
    df['behandlet_fejl'] = df['behandlet_fejl'].astype(str)
    df['behandlet_ok'] = df['behandlet_ok'].astype(str)
    return df


def update_dataframe(df: pd.DataFrame, uuid, failed):
    """Update the dataframe with the status of the element."""
    df.loc[df['uuid'] == uuid, 'behandlet_fejl' if failed else 'behandlet_ok'] = 'x'
    if not failed:
        df.loc[df['uuid'] == uuid, 'behandlet_fejl'] = ' '
    else:
        df.loc[df['uuid'] == uuid, 'behandlet_ok'] = ' '


def get_status_params(form_id: str):
    """
    Generates a set of status parameters for the process, based on the given form_id and JSON arguments.

    Args:
        form_id (str): The unique identifier for the current process.
        case_metadata (dict): A dictionary containing various process-related arguments, including table names.

    Returns:
        tuple: A tuple containing three dictionaries:
            - status_params_inprogress: Parameters indicating that the process is in progress.
            - status_params_success: Parameters indicating that the process completed successfully.
            - status_params_failed: Parameters indicating that the process has failed.
            - status_params_manual: Parameters indicating that the process is handled manually.
    """
    status_params_inprogress = {
        "Status": ("str", "InProgress"),
        "form_id": ("str", f'{form_id}')
    }
    status_params_success = {
        "Status": ("str", "Successful"),
        "form_id": ("str", f'{form_id}')
    }
    status_params_failed = {
        "Status": ("str", "Failed"),
        "form_id": ("str", f'{form_id}')
    }
    status_params_manual = {
        "Status": ("str", "Manual"),
        "form_id": ("str", f'{form_id}')
    }
    return status_params_inprogress, status_params_success, status_params_failed, status_params_manual
