import json
from datetime import datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError

ecr = boto3.client(
    'ecr',
    region_name='us-west-2'
)


def lambda_handler(event, context):
    repo_get()
    return {
        'statusCode': 200,
        'body': json.dumps(
            'Successfull'
        )
    }


# func that describes the available repos to search for results
def repo_get():
    repos = []
    ecrRepos = ecr.describe_repositories()
    for repo in ecrRepos['repositories']:
        repos.append(repo)
    image_parse(repos)


# func that parses out the images to be scanned
def image_parse(repos):
    wrk_list = []
    untagged_images = []
    for repo in repos:
        payload = {}
        images = ecr.describe_images(
            repositoryName=repo['repositoryName']
        )
        registry = repo['registryId']
        repository = repo['repositoryName']
        payload.update(
            {
                'registry': registry,
                'repository': repository
            }
        )
        for image in images['imageDetails']:
            tag = 'imageTags'
            summ = 'imageScanFindingsSummary'
            if tag in image:
                tag = image['imageTags'][0]
                digest = image['imageDigest']
                now = datetime.now(timezone.utc)
                if summ in image:
                    summary = image['imageScanFindingsSummary']
                    lastRun = summary['imageScanCompletedAt']
                else:
                    lastRun = now - timedelta(days=2)
                payload.update(
                    {
                        'tag': tag,
                        'digest': digest,
                        'now': now,
                        'summ': summ,
                        'lastRun': lastRun
                    }
                )
                wrk_list.append(payload)
            else:
                print(
                    f"this image {repository}:{digest} has no tag"
                )
                untagged = f'{repository}:{digest}'
                untagged_images.append(untagged)
    if len(untagged_images) > 0:
        print(f"These untagged images {untagged_images} won't be scanned")
    start_image_scans(wrk_list)


# func that initiates scans on images that have not had a scan within 24 hours
def start_image_scans(wrk_list):
    results = []
    for i in wrk_list:
        registry = i['registry']
        repository = i['repository']
        digest = i['digest']
        tag = i['tag']
        now = i['now']
        lastRun = i['lastRun']
        if (now - lastRun) > timedelta(1):
            try:
                scanresp = ecr.start_image_scan(
                    registryId=registry,
                    repositoryName=repository,
                    imageId={
                        'imageDigest': digest,
                        'imageTag': tag
                    }
                )
                results.append(scanresp)
            except ClientError as err:
                print(err.response['Error']['Message'])
                print(registry, repository, digest, tag)
        else:
            print(f'You have scanned {repository}{tag} within 24 hours')
    print(results)

