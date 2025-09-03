"""This is the main process file for the robot framework."""
import json
import os
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection
from OpenOrchestrator.database.queues import QueueStatus, QueueElement
from mbu_dev_shared_components.utils.db_stored_procedure_executor import execute_stored_procedure

from robot_framework.subprocesses.get_os2form_receipt import fetch_receipt
from robot_framework.subprocesses.outlay_ticket_creation import handle_opus
from robot_framework.subprocesses.helper_functions import handle_post_process, get_status_params


def process(orchestrator_connection: OrchestratorConnection, queue_element, browser) -> None:
    """Main process function."""
    orchestrator_connection.log_trace("Starting the process.")

    os2_api_key = orchestrator_connection.get_credential("os2_api").password
    process_single_queue_element(queue_element, os2_api_key, browser, orchestrator_connection)

    orchestrator_connection.log_trace("Process completed.")


def process_single_queue_element(queue_element: QueueElement, os2_api_key, browser, orchestrator_connection: OrchestratorConnection):
    """Process a single queue element."""
    connection_string = orchestrator_connection.get_constant("DbConnectionString").value
    element_data = json.loads(queue_element.data)
    form_id = element_data['uuid']
    status_params_inprogress, status_params_success, _, _ = get_status_params(form_id)
    orchestrator_connection.set_queue_element_status(queue_element.id, QueueStatus.IN_PROGRESS)
    orchestrator_connection.log_trace(f"Processing queue element ID: {queue_element.id}")
    execute_stored_procedure(
        connection_string,
        "journalizing.sp_update_status",
        status_params_inprogress
    )
    folder_path = fetch_receipt(queue_element, os2_api_key, orchestrator_connection)
    handle_opus(queue_element, folder_path, browser, orchestrator_connection)
    remove_attachment_if_exists(folder_path, element_data, orchestrator_connection)
    handle_post_process(False, queue_element, orchestrator_connection, status_params_success)


def remove_attachment_if_exists(folder_path, element_data, orchestrator_connection):
    """Remove the attachment file if it exists."""
    attachment_path = os.path.join(folder_path, f'receipt_{element_data["uuid"]}.pdf')
    if os.path.exists(attachment_path):
        orchestrator_connection.log_trace(f"Removing attachment file: {attachment_path}")
        os.remove(attachment_path)
