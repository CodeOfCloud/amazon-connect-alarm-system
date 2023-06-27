import json
import boto3
import uuid
import time
from datetime import datetime, timezone, timedelta
tz_utc = timezone(timedelta(hours=+0))
tz_sg = timezone(timedelta(hours=+8))

# Global Variable 
InstanceId = "625f763f-0746-494e-96d2-33946b7xxxxx"
ContactFlowId = "274dcac2-ffce-4555-bcff-7ccc79axxxxx"
SourcePhoneNumber = "+661800012345"
QueueUrl = "https://sqs.ap-southeast-1.amazonaws.com/<account-id>/demo_queue_amazon_connect"
ContactInfoTableName = 'connect-contact-info'
EventTableName = 'connect-event-info'
ContactLayer = 3 # contact numbers to call in one round as listed in DynamoDB
RoundCallLimit = 3 # max round to call these 3 numbers
DelaySeconds = 20 # delay between each call in seconds


def lambda_handler(event, context):
    # Get contact number information from DynamoDB
    print('event info - ', event)
    dynamodb = boto3.resource('dynamodb')
    contact_info_table = dynamodb.Table(ContactInfoTableName)
    contact_info = contact_info_table.get_item(
        Key={
            'projectName': 'project1'
        }
    )
    print('contact info - ', contact_info)

    ## example message body
    '''
    {
        "eventId": "optional value for subsequential call only"
        "projectName": 'project1',
        'nextCall': 1, 
        'round': 1,
        'message': 'start call first number'
    }
    '''
    ## Since we configure lambda trigger batch to 1, every time only one message is sent to lambda, so we can get the message body directly
    message_body = json.loads(event['Records'][0]['body'])
    next_call_id= "contactNumber" + str(message_body.get('nextCall', 1))
    destination_phone_number = contact_info['Item'].get(next_call_id, 'contactNumber1')

    # Outbound call using amazon connect
    ## Check if to start the call using round
    if message_body.get('round', 1) > RoundCallLimit:
        return f'Calls already made for {RoundCallLimit} rounds, stop here'

    ## Start outbound call 
    connect_client = boto3.client('connect')
    connect_response = connect_client.start_outbound_voice_contact(
        DestinationPhoneNumber= destination_phone_number,
        InstanceId=InstanceId,
        ContactFlowId=ContactFlowId,
        SourcePhoneNumber=SourcePhoneNumber,
        Attributes={
            'message': message_body.get('message', 'this is a test message'), 
            'is_accepted': 'false'
        },
        AnswerMachineDetectionConfig={
            'EnableAnswerMachineDetection': False,
            'AwaitAnswerMachinePrompt': True
        },
        TrafficType='GENERAL'
    )
    print('start outbound - ', connect_response)
    ## Every outbound call is one contact
    contact_id = connect_response['ContactId']

    ## Log event contactId to DynamoDB
    event_id = str(uuid.uuid4()) if message_body.get('eventId') == None else message_body.get('eventId')
    dynamodb = boto3.resource('dynamodb')
    event_info_table = dynamodb.Table(EventTableName)
    
    ## Calculate the number of contact with multiply rounds , example output ContactId4 on round 2 nextCall 1
    contact_num = message_body.get('nextCall', 1) + (message_body.get('round', 1)-1)*ContactLayer
    contact_num_id = "ContactId" + str(contact_num)

    ## Update event table with contactId
    update_event_response = event_info_table.update_item(
        Key={'eventId': event_id},
        UpdateExpression="set #contact_num_id=:c",
        ExpressionAttributeNames={
            "#contact_num_id": contact_num_id
        },
        ExpressionAttributeValues={
            ':c': contact_id},
        ReturnValues="ALL_NEW")
    print('update even table - ', update_event_response)

    # check if contact is accepted
    ## sleep 65s seconds waiting for connect response as 60s
    time.sleep(65)

    ## If the contact flow attribute is_accept has been updated
    attribute_response = connect_client.get_contact_attributes(
        InstanceId=InstanceId,
        InitialContactId=contact_id
    )
    print('contact attribute - ', attribute_response)
    if attribute_response['Attributes']['is_accepted'] == 'true':
        accept_time = datetime.now(tz_sg).strftime("%Y/%m/%d %H:%M:%S")
        print(f'event {event_id} is accepted on {accept_time}')
        return 'Call picked up'

    # if not pick up, construct message and send to queue
    ## next call number, example: 1, 2, 3
    next_call = 1 if message_body.get('nextCall', 1) == ContactLayer else message_body.get('nextCall', 1) + 1  
    next_round = message_body.get('round', 1) + 1 if message_body.get('nextCall', 1) == ContactLayer else message_body.get('round', 1) 
    queue_message = {
        'eventId': event_id,
        "projectName": message_body.get('projectName', 'project1'),
        'nextCall': next_call, 
        'round': next_round,
        'message': message_body.get('message', 'this is a test message')
    }

    ## Send message to queue
    sqs = boto3.resource('sqs')
    queue = sqs.Queue(QueueUrl)
    response = queue.send_message(
        MessageBody=json.dumps(queue_message),
        DelaySeconds=DelaySeconds # delay after first call missed
    )
    print('send message - ',response)
    return 'Call missed, log message to queue for next person'
