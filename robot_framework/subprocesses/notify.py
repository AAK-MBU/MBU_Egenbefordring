"""Send mail functions"""
import json

from itk_dev_shared_components.smtp.smtp_util import send_email as _send_email
from OpenOrchestrator.orchestrator_connection.connection import OrchestratorConnection

from robot_framework import config


def send_mail(orchestrator_connection: OrchestratorConnection):
    """Function to send email to inputted receiver"""
    proc_args = json.loads(orchestrator_connection.process_arguments)
    receiver = proc_args["notification_email"]
    folder_dest = orchestrator_connection.folder_dest  # Manually set in process()

    folder_url = config.SHAREPOINT_SITE_URL+"teams/"+config.SHAREPOINT_SITE_NAME+"/"+config.DOCUMENT_LIBRARY+"/"+config.DOCUMENT_FOLDER+"/"+folder_dest
    email_subject = "Robotten til egenbefordring er kørt"
    email_body = ('<p>Robotten til egenbefordring er nu kørt '
                  'og oversigten samt eventuelt relevante dokumenter '
                  f'er uploadet til <a href="{folder_url}">{folder_dest}-mappen</a></p>')

    _send_email(
        receiver=receiver,
        sender=orchestrator_connection.get_constant("e-mail_noreply").value,
        subject=email_subject,
        body=email_body,
        smtp_server=orchestrator_connection.get_constant('smtp_server').value,
        smtp_port=orchestrator_connection.get_constant('smtp_port').value,
        html_body=True,
    )

    orchestrator_connection.log_trace(f"E-mail sent to following receiver(s): {', '.join(receiver) if isinstance(receiver, list) else receiver}")
