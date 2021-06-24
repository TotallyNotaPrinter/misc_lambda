import json
from datetime import datetime
from logging import getLogger, INFO
import boto3
from botocore.exceptions import ClientError

ecr = boto3.client('ecr', region_name='us-west-2')
sqs = boto3.client('sqs', region_name='us-west-2')
sns = boto3.client('sns', region_name='us-west-2')

def lambda_handler(event, context):
    print('getting repos')
    repos = repo_get()
    print('building payload')
    payload= construct_payload(repos)
    print(payload)
    print('geting vuln reports')
    results = describe_findings(payload)
    print('shipping results')
    ship_results(results)
    return {
        'statusCode': 200,
        'body': json.dumps('Successfull')
    }

def repo_get(): 
        repos = [] 
        ecrRepos = ecr.describe_repositories()
        for repo in ecrRepos['repositories']:
            repos.append(repo)
        return repos

def construct_payload(repos): 
    images = []
    payload = []
    null = []
    for i in repos:
        registry = i['registryId'] 
        repository = i['repositoryName'] 
        image = ecr.describe_images(repositoryName=i['repositoryName'])
        images.append(image)
    for i in images:
        description = i['imageDetails'][0]['imageScanStatus']['description']
        if description == 'UnsupportedImageError: The operating system and/or package manager are not supported.':
            print('this image is not supported as of this time')
        elif description != 'UnsupportedImageError: The operating system and/or package manager are not supported.':
            o = {
                'digest': i['imageDetails'][0]['imageDigest'],
                'tag': i['imageDetails'][0]['imageTags'][0],
                'repository': i['imageDetails'][0]['repositoryName'],
                'registry': i['imageDetails'][0]['registryId']
            }
            payload.append(o)
    return(payload)


def describe_findings(payload):
    results = []
    print(len(payload))
    for i in payload:
        try:
            resultresp = ecr.describe_image_scan_findings(
                registryId = i['registry'],
                repositoryName = i['repository'],
                imageId={
                    'imageDigest': i['digest'],
                    'imageTag': i['tag']
                }
            )
            results.append(resultresp)
        except ClientError as err:
            print(err.response['Error']['Message'])
            print(registry,repository,digest,tag)
    print(len(results))
    return results

def ship_results(results):
    for result in results:
        try:
            msg = json.dumps(result, indent=4, default=str)
            msgresp = sqs.send_message(
                QueueUrl='https://sqs.us-west-2.amazonaws.com/041706332677/test-splunk-ecr-vulnscan',
                MessageBody= msg
            )
        except ClientError as err:
            print(err.response['Error']['Message'])

