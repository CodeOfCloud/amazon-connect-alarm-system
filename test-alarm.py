import boto3
import json
from botocore.config import Config
import datetime
my_config = Config(
    signature_version='v4'
)
current_time = datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
event_id = 'test-event-message-' + current_time
QueueUrl="<SQS queue url>"
queue_message = {
    "eventId": event_id,
    "projectName": 'project1',
    'nextCall': 1, 
    'round': 1,
    'message': 'demo call through Amazon Connect'
}

session = boto3.Session(profile_name='demo-connect-user')
sqs = session.resource('sqs', config=my_config)
queue = sqs.Queue(QueueUrl)
response = queue.send_message(
    MessageBody=json.dumps(queue_message),
    DelaySeconds=5
)
print(response)
